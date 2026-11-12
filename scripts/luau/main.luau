local config = require("dusklight.config")
local overlay = require("dusklight.overlay")
local ui = require("dusklight.ui")
local log = require("dusklight.log")
local host = require("dusklight.host")

local opts = require("./options")

local translation_var = config.register({
    name = "translation",
    type = "string",
    default = opts.default_translation,
})
local locales_var = config.register({
    name = "locales",
    type = "string",
    default = opts.default_locales,
})

local translation_by_key = {}
local locale_known = {}
for _, item in ipairs(opts.translations) do
    translation_by_key[item.key] = item
end
for _, item in ipairs(opts.locales) do
    locale_known[item.code] = true
end

local handles = {}

local function clear()
    for _, handle in ipairs(handles) do
        pcall(function()
            handle:remove()
        end)
    end
    handles = {}
end

local function current_translation()
    local key = translation_var:get()
    if translation_by_key[key] then
        return key
    end
    return opts.default_translation
end

local function selected_locales()
    local out, seen = {}, {}
    for code in string.gmatch(locales_var:get() or "", "[^,%s]+") do
        if locale_known[code] and not seen[code] then
            seen[code] = true
            table.insert(out, code)
        end
    end
    return out
end

local function apply()
    clear()
    local codes = selected_locales()
    if #codes == 0 then
        log.info("no game language selected, nothing overlaid")
        return
    end
    local translation = current_translation()
    for _, code in ipairs(codes) do
        for _, name in ipairs(opts.msg_files) do
            table.insert(handles,
                overlay.add_file("/res/Msg" .. code .. "/" .. name,
                    "res/" .. translation .. "/" .. name))
        end
    end
    for _, region in ipairs(opts.font_regions) do
        for _, name in ipairs(opts.font_files) do
            table.insert(handles,
                overlay.add_file("/res/Font" .. region .. "/" .. name,
                    "res/" .. translation .. "/" .. name))
        end
    end
    log.info(string.format("overlaid %d files: %s + %s", #handles, translation,
        table.concat(codes, ",")))
end

local function reapply()
    local ok, err = pcall(apply)
    if not ok then
        log.error("overlay failed: " .. tostring(err))
    end
end

local function set_locale(code, enabled)
    local out = {}
    for _, existing in ipairs(selected_locales()) do
        if existing ~= code then
            table.insert(out, existing)
        end
    end
    if enabled then
        table.insert(out, code)
    end
    locales_var:set(table.concat(out, ","))
end

translation_var:subscribe(reapply)
locales_var:subscribe(reapply)

ui.register_mods_panel({
    build = function(panel)
        panel:add_text(opts.ui.hint)

        local labels = {}
        for _, item in ipairs(opts.translations) do
            table.insert(labels, item.label)
        end
        panel:add_control({
            kind = "dropdown",
            label = opts.ui.label_translation,
            options = labels,
            get = function()
                return translation_by_key[current_translation()].offset
            end,
            -- 控件回传的 int_value 在 LuauIntegerType2 下是 integer，与 number 不能相加或比较，
            -- 所以按字符串查表
            set = function(value)
                local key = opts.translation_by_offset[tostring(value)]
                if key then
                    translation_var:set(key)
                end
            end,
        })

        panel:add_section(opts.ui.section_locale)
        for _, item in ipairs(opts.locales) do
            local code = item.code
            panel:add_control({
                kind = "toggle",
                label = item.label,
                get = function()
                    for _, existing in ipairs(selected_locales()) do
                        if existing == code then
                            return true
                        end
                    end
                    return false
                end,
                set = function(value)
                    set_locale(code, value)
                end,
            })
        end
    end,
})

host.on_shutdown(clear)

reapply()
