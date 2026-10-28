-- ff7-ime_filter.lua
-- 魔光键影 · 按键过滤 processor。
--
-- 目标：本方案只接收拼音字母与音节分隔符。数字、标点、符号、空格等
-- 可打印字符在不承担输入法功能时直接吞掉，避免落入游戏或宿主程序。
--
-- schema 接线：- lua_processor@*ff7-ime_filter
--
-- libRime processor 返回值：
--   0 = kRejected：停止处理链，按键交给宿主程序
--   1 = kAccepted：按键已被本方案消费
--   2 = kNoop：继续交给后面的 processor
--
-- 保留的功能键：
--   * 字母与组合中的 '（音节分隔符）交给 speller；
--   * 组合中的空格、回车、退格、Esc、方向键交给 express_editor/selector；
--   * 候选菜单展开时，主键盘 1-9 交给 selector 选词；
--   * 其余控制键（Ctrl/Alt 组合、Tab、F 键等）不拦截。

local M = {}

local ACCEPT = 1
local NOOP = 2

local KEY_SPACE = 0x20
local KEY_APOSTROPHE = 0x27
local KEY_1 = 0x31
local KEY_9 = 0x39

local KP_0 = 0xFFB0
local KP_9 = 0xFFB9
local KP_MULTIPLY = 0xFFAA
local KP_ADD = 0xFFAB
local KP_SEPARATOR = 0xFFAC
local KP_SUBTRACT = 0xFFAD
local KP_DECIMAL = 0xFFAE
local KP_DIVIDE = 0xFFAF
local KP_EQUAL = 0xFFBD

local function is_letter(kc)
  return (kc >= 0x41 and kc <= 0x5A) or (kc >= 0x61 and kc <= 0x7A)
end

local function is_printable(kc)
  return kc >= 0x20 and kc <= 0x7E
end

local function is_keypad_digit(kc)
  return kc >= KP_0 and kc <= KP_9
end

local function is_keypad_symbol(kc)
  return kc == KP_MULTIPLY or kc == KP_ADD or kc == KP_SEPARATOR
      or kc == KP_SUBTRACT or kc == KP_DECIMAL or kc == KP_DIVIDE
      or kc == KP_EQUAL
end

local function key_method(key, name)
  local fn = key and key[name]
  if type(fn) ~= "function" then
    return nil
  end
  local ok, value = pcall(fn, key)
  if ok then
    return value
  end
  return nil
end

local function context_value(ctx, name, default)
  if not ctx then
    return default
  end
  local ok, value = pcall(function() return ctx[name] end)
  if ok and value ~= nil then
    return value
  end
  return default
end

local function context_call(ctx, name, default)
  if not ctx then
    return default
  end
  local fn = ctx[name]
  if type(fn) ~= "function" then
    return default
  end
  local ok, value = pcall(fn, ctx)
  if ok then
    return value
  end
  return default
end

function M.func(key, env)
  if key_method(key, "release") then
    return NOOP
  end
  if key_method(key, "ctrl") or key_method(key, "alt")
      or key_method(key, "super") then
    return NOOP
  end

  local kc = key.keycode
  if is_letter(kc) then
    return NOOP
  end

  local ctx = env and env.engine and env.engine.context or nil

  if kc == KEY_APOSTROPHE then
    -- 只在组合中、且前一个字符是字母时放行；空闲或连续分隔符直接吞掉。
    local input = context_value(ctx, "input", "")
    if type(input) == "string" and #input > 0
        and input:sub(-1):match("%a") then
      return NOOP
    end
    return ACCEPT
  end

  if kc == KEY_SPACE then
    if context_call(ctx, "is_composing", false) then
      return NOOP
    end
    return ACCEPT
  end

  -- 主键盘 1-9：只在候选菜单展开时用于选词，其余情况不落字。
  if kc >= KEY_1 and kc <= KEY_9 then
    if context_call(ctx, "has_menu", false) then
      return NOOP
    end
    return ACCEPT
  end

  -- 小键盘数字与运算符没有选词用途，始终吞掉。
  if is_keypad_digit(kc) or is_keypad_symbol(kc) then
    return ACCEPT
  end

  -- 其余可打印字符（0、标点、符号等）一律吞掉。
  if is_printable(kc) then
    return ACCEPT
  end

  -- 控制键、导航键、F 键等保持透传。
  return NOOP
end

return M
