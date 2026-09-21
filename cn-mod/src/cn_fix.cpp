#include "mods/service.hpp"
#include "mods/svc/hook.h"
#include "mods/svc/hook.hpp"
#include "mods/svc/log.h"

#include "JSystem/J2DGraph/J2DTextBox.h"
#include "JSystem/JUtility/JUTResFont.h"

DEFINE_MOD();

IMPORT_SERVICE(LogService, svc_log);
IMPORT_SERVICE(HookService, svc_hook);

DEFINE_HOOK_SYMBOL("?draw@J2DTextBox@@UEAAXMM@Z", void(J2DTextBox*, f32, f32), DrawA);
    static int logged = 0;
    if (logged >= 400 || box == NULL) {
        return;
    }
    ++logged;
    char hex[48];
    hex[0] = 0;
    if (box->mStringPtr != NULL) {
        u32 n = box->mStringLength < 8 ? (u32)box->mStringLength : 8;
        for (u32 i = 0; i < n; ++i) {
            snprintf(hex + i * 3, 4, "%02x ", (u8)box->mStringPtr[i]);
        }
    }
    char msg[240];
    snprintf(msg, sizeof(msg), "%s alloc=%u bytes: %s", tag, (u32)box->mStringLength, hex);
    svc_log->info(mod_ctx, msg);
}

DEFINE_HOOK_SYMBOL("?draw@J2DTextBox@@UEAAXMM@Z", void(J2DTextBox*, f32, f32), DrawA);
DEFINE_HOOK_SYMBOL("?draw@J2DTextBox@@UEAAXMMMW4J2DTextBoxHBinding@@@Z",
                   void(J2DTextBox*, f32, f32, f32, int), DrawB);
DEFINE_HOOK_SYMBOL("?draw@J2DTextBoxEx@@UEAAXMM@Z", void(J2DTextBox*, f32, f32), DrawExA);
DEFINE_HOOK_SYMBOL("?draw@J2DTextBoxEx@@UEAAXMMMW4J2DTextBoxHBinding@@@Z",
                   void(J2DTextBox*, f32, f32, f32, int), DrawExB);

static HookAction on_draw_a(ModContext*, void* args, void*, void*) {
    log_box("drawA", mods::arg<J2DTextBox*>(args, 0));
    return HOOK_CONTINUE;
}

static HookAction on_draw_ex(ModContext*, void* args, void*, void*) {
    log_box("drawEx", mods::arg<J2DTextBox*>(args, 0));
    return HOOK_CONTINUE;
}

DEFINE_HOOK_SYMBOL("?getString@dMsgStringBase_c@@UEAAMIPEAVJ2DTextBox@@0PEAVJUTFont@@PEAVCOutFont_c@@E@Z",
                   float(void*, u32, J2DTextBox*, J2DTextBox*, void*, void*, u8), GetString);
DEFINE_HOOK_SYMBOL("?draw@COutFont_c@@UEAAXPEAVJ2DTextBox@@MMM@Z",
                   void(void*, J2DTextBox*, f32, f32, f32), OutFontDraw);

static void on_get_string(ModContext*, void* args, void*, void*) {
    log_box("getStr pane1", mods::arg<J2DTextBox*>(args, 2));
    log_box("getStr pane2", mods::arg<J2DTextBox*>(args, 3));
}

static HookAction on_out_font_draw(ModContext*, void* args, void*, void*) {
    log_box("outFontDraw", mods::arg<J2DTextBox*>(args, 1));
    return HOOK_CONTINUE;
}

DEFINE_HOOK_SYMBOL("?fpcM_Execute@@YAHPEAX@Z", int(void*), ExecProbe);
DEFINE_HOOK_SYMBOL("?print@J2DPrint@@QEAAMMMEPEBDZZ",
                   float(void*, f32, f32, u8, const char*, const char*), J2DPrintA);
DEFINE_HOOK_SYMBOL("?drawChar_scale@JUTResFont@@UEAAMMMMMH_NPEAUFontDrawContext@@@Z",
                   float(void*, f32, f32, f32, f32, int, bool, void*), DrawChar);
DEFINE_HOOK_SYMBOL(
    "?getStringPageLocal@dMsgStringBase_c@@QEAAMIEEPEAVJ2DTextBox@@0PEAVJUTFont@@PEAVCOutFont_c@@E@Z",
    float(void*, u32, u8, u8, J2DTextBox*, J2DTextBox*, void*, void*, u8), GetStringPage);
DEFINE_HOOK_SYMBOL("?drawFontLocal@dMsgStringBase_c@@UEAAXPEAVJ2DTextBox@@EMMMMIE@Z",
                   void(void*, J2DTextBox*, u8, f32, f32, f32, f32, u32, u8), DrawFontBase);
DEFINE_HOOK_SYMBOL("?drawFontLocal@dMsgString_c@@UEAAXPEAVJ2DTextBox@@EMMMMIE@Z",
                   void(void*, J2DTextBox*, u8, f32, f32, f32, f32, u32, u8), DrawFontDerived);

static HookAction on_draw_char(ModContext*, void* args, void*, void*) {
    static int n = 0;
    if (n >= 200) {
        return HOOK_CONTINUE;
    }
    ++n;
    int code = mods::arg<int>(args, 5);
    char msg[96];
    snprintf(msg, sizeof(msg), "glyph U+%04X", code & 0xFFFF);
    svc_log->info(mod_ctx, msg);
    return HOOK_CONTINUE;
}

DEFINE_HOOK_SYMBOL("?drawString_size_scale@JUTFont@@QEAAMMMMMPEBDI_N@Z",
                   float(void*, f32, f32, f32, f32, const char*, u32, bool), DrawStringSS);

static HookAction on_draw_string_ss(ModContext*, void* args, void*, void*) {
    static int n = 0;
    if (n >= 40) {
        return HOOK_CONTINUE;
    }
    ++n;
    const char* str = mods::arg<const char*>(args, 5);
    u32 usz = mods::arg<u32>(args, 6);
    char hex[64];
    hex[0] = 0;
    if (str != NULL) {
        for (u32 i = 0; i < 12; ++i) {
            snprintf(hex + i * 3, 4, "%02x ", (u8)str[i]);
        }
    }
    char msg[220];
    snprintf(msg, sizeof(msg), "drawStringSS usz=%u bytes: %s", usz, hex);
    svc_log->info(mod_ctx, msg);
    return HOOK_CONTINUE;
}

static HookAction on_draw_font(ModContext*, void* args, void*, void*) {
    static int n = 0;
    J2DTextBox* box = mods::arg<J2DTextBox*>(args, 1);
    if (n < 60) {
        ++n;
        char msg[96];
        snprintf(msg, sizeof(msg), "drawFont count=%u flags=%u", mods::arg<u32>(args, 7),
                 (u32)mods::arg<u8>(args, 8));
        svc_log->info(mod_ctx, msg);
        log_box("  drawFont pane", box);
    }
    return HOOK_CONTINUE;
}

static void on_get_string_page(ModContext*, void* args, void*, void*) {
    static int n = 0;
    if (n >= 60) {
        return;
    }
    ++n;
    char msg[96];
    snprintf(msg, sizeof(msg), "getStrPage id=%u page=%u", mods::arg<u32>(args, 1),
             (u32)mods::arg<u8>(args, 2));
    svc_log->info(mod_ctx, msg);
    log_box("  getStrPage pane1", mods::arg<J2DTextBox*>(args, 4));
    log_box("  getStrPage pane2", mods::arg<J2DTextBox*>(args, 5));
}

static HookAction on_j2dprint(ModContext*, void* args, void*, void*) {
    static int n = 0;
    if (n >= 200) {
        return HOOK_CONTINUE;
    }
    const char* fmt = mods::arg<const char*>(args, 4);
    if (fmt == NULL) {
        return HOOK_CONTINUE;
    }
    ++n;
    char msg[260];
    if (strstr(fmt, "%s") != NULL) {
        const char* text = mods::arg<const char*>(args, 5);
        char hex[48];
        hex[0] = 0;
        if (text != NULL) {
            for (u32 i = 0; i < 8; ++i) {
                snprintf(hex + i * 3, 4, "%02x ", (u8)text[i]);
            }
        }
        snprintf(msg, sizeof(msg), "j2dprint fmt=%s bytes: %s", fmt, hex);
    } else {
        snprintf(msg, sizeof(msg), "j2dprint fmt=%s", fmt);
    }
    svc_log->info(mod_ctx, msg);
    return HOOK_CONTINUE;
}

static HookAction on_exec_probe(ModContext*, void*, void*, void*) {
    static int n = 0;
    if (n < 20) {
        ++n;
        svc_log->info(mod_ctx, "PROBE fpcM_Execute fired");
    }
    return HOOK_CONTINUE;
}

extern "C" {

MOD_EXPORT ModResult mod_initialize(ModError* error) {
    UNUSED(error);
    ModResult d1 = mods::hook::add_pre<DrawA>(on_draw_a);
    ModResult d2 = mods::hook::add_pre<DrawB>(on_draw_a);
    ModResult d3 = mods::hook::add_pre<DrawExA>(on_draw_ex);
    ModResult d4 = mods::hook::add_pre<DrawExB>(on_draw_ex);
    char dbg[160];
    snprintf(dbg, sizeof(dbg), "draw hooks: %d %d %d %d (0=ok)", (int)d1, (int)d2, (int)d3, (int)d4);
    svc_log->info(mod_ctx, dbg);
    ModResult g1 = mods::hook::add_post<GetString>(on_get_string);
    ModResult g2 = mods::hook::add_pre<OutFontDraw>(on_out_font_draw);
    ModResult g3 = mods::hook::add_pre<ExecProbe>(on_exec_probe);
    ModResult g4 = mods::hook::add_pre<J2DPrintA>(on_j2dprint);
    ModResult g5 = mods::hook::add_pre<DrawChar>(on_draw_char);
    ModResult g6 = mods::hook::add_post<GetStringPage>(on_get_string_page);
    ModResult g7 = mods::hook::add_pre<DrawFontBase>(on_draw_font);
    ModResult g8 = mods::hook::add_pre<DrawFontDerived>(on_draw_font);
    ModResult g9 = mods::hook::add_pre<DrawStringSS>(on_draw_string_ss);
    snprintf(dbg, sizeof(dbg), "hooks: %d %d probe: %d j2dprint: %d glyph: %d page: %d drawFont: %d strSS: %d",
             (int)g1, (int)g2, (int)g3, (int)g4, (int)g5, (int)g6, (int)g7, (int)g9);
    svc_log->info(mod_ctx, dbg);
    snprintf(dbg, sizeof(dbg), "drawFontDerived: %d (0=ok)", (int)g8);
    svc_log->info(mod_ctx, dbg);
    svc_log->info(mod_ctx, "cn.font.fix active (J2DTextBox text length)");
    return MOD_OK;
}

MOD_EXPORT ModResult mod_update(ModError*) {
    return MOD_OK;
}

MOD_EXPORT ModResult mod_shutdown(ModError*) {
    return MOD_OK;
}
}
