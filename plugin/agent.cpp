// 検証用の汎用プラグイン。
// 環境変数 AVIUTL2_PYRRHULINA_JOB が指すジョブファイルの命令を順に実行し、
// 結果を「<ジョブファイル>.result」に書いてから AviUtl2 を閉じる。
// 環境変数が無いときは何もしないので、通常の起動には影響しない。
//
// ジョブファイル（UTF-8、タブ区切り、1行1命令）:
//   timeout <ミリ秒>                以降の命令すべてに使える残り時間を設定する
//   project <プロジェクトのパス>    起動引数で渡したプロジェクトの読み込み完了を待つ
//   render  <フレーム番号>  <出力ファイルのパス>
// 結果ファイル（命令と同じ順）:
//   ok      [<幅>  <高さ>]
//   error   <理由>
// 画像ファイル: int32 の 幅・高さ・pitch に続けて、pitch×高さ バイトの RGBA。
//
// プロジェクトは起動引数で開く。EDIT_HANDLE::open_project_file() は 2.1.17 で
// 呼ぶと AviUtl2 が落ちた（EndDraw の例外。原因は未特定）ので使っていない。

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <exception>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

// SDK のヘッダーは AviUtl2 本体より新しいことがある。本体に無い関数を呼ぶと落ちるので、
// 使う関数が追加された時期を SDK の CHANGELOG で確認すること。
#include "aviutl2_sdk/plugin2.h"
#include "aviutl2_sdk/logger2.h"

namespace {

constexpr DWORD kDefaultTimeoutMs = 60000;
// 動くことを e2e で確かめた一番古い本体のバージョン（2.1.17）。使う API を増やしたときだけ上げる。
// 形式は obj.getinfo("version") と同じ（2.1.17 なら 2011700）。
constexpr DWORD kRequiredVersion = 2011700;
constexpr UINT kCallMessage = WM_APP + 1;

EDIT_HANDLE* g_edit = nullptr;
LOG_HANDLE* g_logger = nullptr;
HWND g_main_thread_window = nullptr;
// InitializePlugin で受け取った本体のバージョン番号。証跡としてログに出す。
DWORD g_host_version = 0;
std::wstring g_job_path;
// これを過ぎたら、残りの命令は待たずに失敗にする。
ULONGLONG g_deadline = 0;

CRITICAL_SECTION g_loaded_lock;
std::wstring g_loaded_project;
HANDLE g_loaded_changed = nullptr;

std::wstring widen(const std::string& utf8) {
	if (utf8.empty()) return {};
	int n = MultiByteToWideChar(CP_UTF8, 0, utf8.data(), (int)utf8.size(), nullptr, 0);
	std::wstring w(n, L'\0');
	MultiByteToWideChar(CP_UTF8, 0, utf8.data(), (int)utf8.size(), w.data(), n);
	return w;
}

void log_info(const std::wstring& message) {
	if (g_logger) g_logger->info(g_logger, (L"[pyrrhulina] " + message).c_str());
}

DWORD remaining_ms() {
	ULONGLONG now = GetTickCount64();
	return now >= g_deadline ? 0 : (DWORD)(g_deadline - now);
}

std::vector<std::string> split_tabs(const std::string& line) {
	std::vector<std::string> fields;
	std::stringstream stream(line);
	std::string field;
	while (std::getline(stream, field, '\t')) fields.push_back(field);
	return fields;
}

// EDIT_HANDLE の関数はメインスレッドから呼ぶ。メインスレッドが持つウィンドウへ
// メッセージを送ることで、ワーカースレッドからの呼び出しをメインスレッドに移す。
struct MainThreadCall {
	bool (*func)(void* param);
	void* param;
};

enum class CallResult { Succeeded, Failed, TimedOut };

LRESULT CALLBACK main_thread_window_proc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
	if (message == kCallMessage) {
		auto* call = reinterpret_cast<MainThreadCall*>(lparam);
		return call->func(call->param) ? 1 : 0;
	}
	return DefWindowProcW(hwnd, message, wparam, lparam);
}

// TimedOut のとき、メッセージは後から処理されることがある。
// そのため call は解放しない。呼び出し側も param を解放してはいけない。
CallResult on_main_thread(bool (*func)(void* param), void* param) {
	DWORD timeout = remaining_ms();
	if (timeout == 0) return CallResult::TimedOut;
	auto* call = new MainThreadCall{func, param};
	DWORD_PTR succeeded = 0;
	if (!SendMessageTimeoutW(g_main_thread_window, kCallMessage, 0, reinterpret_cast<LPARAM>(call), SMTO_NORMAL, timeout, &succeeded)) {
		return CallResult::TimedOut;
	}
	delete call;
	return succeeded ? CallResult::Succeeded : CallResult::Failed;
}

// 起動時の初期化でも呼ばれる（そのときはパスが空）。
void on_project_load(PROJECT_FILE* project) {
	LPCWSTR path = project->get_project_file_path();
	EnterCriticalSection(&g_loaded_lock);
	g_loaded_project = path ? path : L"";
	LeaveCriticalSection(&g_loaded_lock);
	SetEvent(g_loaded_changed);
}

std::string run_project(const std::vector<std::string>& args) {
	if (args.size() != 2) return "error\tbad arguments";
	std::wstring expected = widen(args[1]);
	for (;;) {
		EnterCriticalSection(&g_loaded_lock);
		bool loaded = lstrcmpiW(g_loaded_project.c_str(), expected.c_str()) == 0;
		ResetEvent(g_loaded_changed);
		LeaveCriticalSection(&g_loaded_lock);
		if (loaded) return "ok";
		if (remaining_ms() == 0) return "error\tproject load timeout";
		WaitForSingleObject(g_loaded_changed, remaining_ms());
	}
}

struct RenderRequest {
	int frame = 0;
	std::wstring out_path;
	HANDLE done = nullptr;
	bool written = false;
	int width = 0;
	int height = 0;
};

// イベント通知スレッドから呼ばれる。buffer はこの関数の中でしか使えない。
void on_rendered(void* param, int, const void* buffer, int width, int height, int pitch) {
	auto* request = static_cast<RenderRequest*>(param);
	request->width = width;
	request->height = height;
	if (FILE* file = _wfopen(request->out_path.c_str(), L"wb")) {
		int header[3] = {width, height, pitch};
		size_t size = (size_t)pitch * (size_t)height;
		request->written = fwrite(header, sizeof(header), 1, file) == 1 && fwrite(buffer, 1, size, file) == size;
		fclose(file);
	}
	SetEvent(request->done);
}

std::string run_render(const std::vector<std::string>& args) {
	if (args.size() != 3) return "error\tbad arguments";
	int frame = std::stoi(args[1]);  // 数字でなければ例外になる（worker が捕まえる）
	auto* request = new RenderRequest;
	request->frame = frame;
	request->out_path = widen(args[2]);
	request->done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
	CallResult requested = on_main_thread([](void* param) {
		return g_edit->rendering_scene_video(static_cast<RenderRequest*>(param)->frame, param, on_rendered);
	}, request);
	std::string result;
	if (requested == CallResult::TimedOut) {
		return "error\tmain thread did not respond";
	} else if (requested == CallResult::Failed) {
		// フレーム番号がシーンの範囲外のときもここに来る。
		result = "error\trendering_scene_video failed";
	} else if (WaitForSingleObject(request->done, remaining_ms()) != WAIT_OBJECT_0) {
		// 後からコールバックが来ても壊れないよう、request は解放しない。
		return "error\trendering timeout";
	} else if (!request->written) {
		result = "error\tcannot write image file";
	} else {
		result = "ok\t" + std::to_string(request->width) + "\t" + std::to_string(request->height);
	}
	CloseHandle(request->done);
	delete request;
	return result;
}

std::string run_command(const std::vector<std::string>& args) {
	if (args[0] == "timeout" && args.size() == 2) {
		g_deadline = GetTickCount64() + std::stoul(args[1]);
		return "ok";
	}
	// 時間切れになった描画がまだ動いているので、続けて実行しても別の理由で失敗するだけになる。
	if (remaining_ms() == 0) return "error\tskipped because the time limit was reached";
	if (args[0] == "project") return run_project(args);
	if (args[0] == "render") return run_render(args);
	return "error\tunknown command";
}

// 結果ファイルは 1 行 1 結果、項目はタブ区切りなので、例外の説明から改行とタブを除く。
std::string single_line(std::string text) {
	for (char& c : text) {
		if (c == '\r' || c == '\n' || c == '\t') c = ' ';
	}
	return text;
}

DWORD WINAPI worker(void*) {
	std::vector<std::string> results;
	std::ifstream job(g_job_path.c_str());
	std::string line;
	while (std::getline(job, line)) {
		if (!line.empty() && line.back() == '\r') line.pop_back();
		if (line.empty()) continue;
		auto args = split_tabs(line);
		log_info(widen(line));
		// ワーカースレッドで例外を捕まえないと std::terminate になり、AviUtl2 ごと落ちる。
		try {
			results.push_back(run_command(args));
		} catch (const std::exception& error) {
			results.push_back("error\texception: " + single_line(error.what()));
		} catch (...) {
			results.push_back("error\tunknown exception");
		}
	}

	// 書きかけの結果を読まれないよう、別名で書いてから改名する。
	std::wstring result_path = g_job_path + L".result";
	std::wstring temp_path = result_path + L".tmp";
	{
		std::ofstream out(temp_path.c_str(), std::ios::binary);
		for (const auto& result : results) out << result << "\n";
	}
	MoveFileExW(temp_path.c_str(), result_path.c_str(), MOVEFILE_REPLACE_EXISTING);

	PostMessageW(g_edit->get_host_app_window(), WM_CLOSE, 0, 0);
	return 0;
}

}  // namespace

EXTERN_C __declspec(dllexport) COMMON_PLUGIN_TABLE* GetCommonPluginTable(void) {
	static COMMON_PLUGIN_TABLE table = {L"aviutl2-pyrrhulina agent", L"aviutl2-pyrrhulina agent"};
	return &table;
}

// これより古い本体では、AviUtl2 がこのプラグインを読み込まない。
EXTERN_C __declspec(dllexport) DWORD RequiredVersion() {
	return kRequiredVersion;
}

EXTERN_C __declspec(dllexport) bool InitializePlugin(DWORD version) {
	g_host_version = version;
	return true;
}

EXTERN_C __declspec(dllexport) void InitializeLogger(LOG_HANDLE* logger) {
	g_logger = logger;
}

EXTERN_C __declspec(dllexport) void RegisterPlugin(HOST_APP_TABLE* host) {
	wchar_t job_path[32768];
	DWORD length = GetEnvironmentVariableW(L"AVIUTL2_PYRRHULINA_JOB", job_path, 32768);
	if (length == 0 || length >= 32768) return;
	g_job_path = job_path;
	g_deadline = GetTickCount64() + kDefaultTimeoutMs;
	log_info(L"host version " + std::to_wstring(g_host_version));

	InitializeCriticalSection(&g_loaded_lock);
	g_loaded_changed = CreateEventW(nullptr, TRUE, FALSE, nullptr);
	g_edit = host->create_edit_handle();
	host->register_project_load_handler(on_project_load);

	WNDCLASSW window_class = {};
	window_class.lpfnWndProc = main_thread_window_proc;
	window_class.hInstance = GetModuleHandleW(nullptr);
	window_class.lpszClassName = L"aviutl2_pyrrhulina_agent";
	RegisterClassW(&window_class);
	g_main_thread_window = CreateWindowExW(0, window_class.lpszClassName, L"", 0, 0, 0, 0, 0, HWND_MESSAGE, nullptr, window_class.hInstance, nullptr);

	CloseHandle(CreateThread(nullptr, 0, worker, nullptr, 0, nullptr));
}
