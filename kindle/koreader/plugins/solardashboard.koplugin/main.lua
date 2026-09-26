local Device = require("device")
local Geom = require("ui/geometry")
local ImageWidget = require("ui/widget/imagewidget")
local InfoMessage = require("ui/widget/infomessage")
local Input = Device.input
local InputContainer = require("ui/widget/container/inputcontainer")
local NetworkMgr = require("ui/network/manager")
local PluginShare = require("pluginshare")
local RenderImage = require("ui/renderimage")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local http = require("socket.http")
local socket = require("socket")
local json = require("json")
local lfs = require("libs/libkoreader-lfs")
local logger = require("logger")

-- RAM-backed: a new picture every few seconds would wear out the Kindle's flash storage.
local directory = "/tmp/solar-dashboard"
local trigger = "/mnt/us/koreader/settings/solar-dashboard-start"
local config_path = "settings/solar-dashboard.json"
local png_signature = string.char(137) .. "PNG\r\n" .. string.char(26) .. "\n"

local DashboardView = InputContainer:extend{}

function DashboardView:init()
    self.dimen = Geom:new{ x = 0, y = 0, w = Device.screen:getWidth(), h = Device.screen:getHeight() }
    self[1] = ImageWidget:new{
        image = self.image,
        image_disposable = true,
        width = self.dimen.w,
        height = self.dimen.h,
        alpha = false,
    }
    self.key_events = { Close = { { Input.group.Back } } }
end

function DashboardView:onClose()
    self.owner:stop()
    return true
end

local SolarDashboard = WidgetContainer:extend{
    name = "solardashboard",
    is_doc_only = false,
}

function SolarDashboard:init()
    self.ui.menu:registerToMainMenu(self)
    self.refresh_task = function() self:refresh() end
    if lfs.attributes(trigger, "mode") == "file" then
        os.remove(trigger)
        UIManager:nextTick(function() self:start() end)
    end
end

function SolarDashboard:addToMainMenu(items)
    items.solar_dashboard = {
        text = "Solar dashboard",
        sorting_hint = "tools",
        callback = function() self:start() end,
    }
end

function SolarDashboard:loadConfig()
    local file = assert(io.open(config_path, "rb"), "Solar dashboard is not configured")
    local config = json.decode(file:read("*all"))
    file:close()
    assert(type(config.url) == "string" and config.url:match("^http://[%d%.]+:%d+/dashboard%.png$"), "Invalid dashboard URL")
    assert(type(config.token) == "string" and #config.token >= 32, "Invalid dashboard token")
    -- The Kindle stays on mains power with Wi-Fi on, so it asks for the next picture a second after
    -- each one is on screen. The Pi switches the solar and home charts every 10 seconds.
    config.interval = tonumber(config.interval) or 1
    assert(config.interval >= 1, "Refresh interval must be at least 1 second")
    -- Fast partial e-ink updates leave ghosting; a full flash every so many pictures clears it.
    config.full_refresh_every = math.floor(tonumber(config.full_refresh_every) or 100)
    assert(config.full_refresh_every >= 1, "full_refresh_every must be at least 1")
    return config
end

function SolarDashboard:keepAwake()
    if self.awake then return end
    self.previous_keepalive = PluginShare.keepalive
    self.previous_pause_auto_suspend = PluginShare.pause_auto_suspend
    PluginShare.keepalive = true
    PluginShare.pause_auto_suspend = true
    UIManager:preventStandby()
    if Device:isKindle() then
        os.execute("lipc-set-prop com.lab126.powerd preventScreenSaver 1")
    end
    self.awake = true
end

function SolarDashboard:restoreSleep()
    if not self.awake then return end
    UIManager:allowStandby()
    PluginShare.keepalive = self.previous_keepalive
    PluginShare.pause_auto_suspend = self.previous_pause_auto_suspend
    if Device:isKindle() and not self.previous_keepalive then
        os.execute("lipc-set-prop com.lab126.powerd preventScreenSaver 0")
    end
    self.awake = false
end

function SolarDashboard:setLandscape()
    self.previous_rotation = Device.screen:getRotationMode()
    if Device.screen:getWidth() < Device.screen:getHeight() then
        Device.screen:setRotationMode(Device.screen.DEVICE_ROTATED_CLOCKWISE)
    end
end

function SolarDashboard:restoreRotation()
    if self.previous_rotation ~= nil and Device.screen:getRotationMode() ~= self.previous_rotation then
        Device.screen:setRotationMode(self.previous_rotation)
        UIManager:setDirty(nil, "full")
    end
    self.previous_rotation = nil
end

function SolarDashboard:scheduleNext(seconds)
    UIManager:unschedule(self.refresh_task)
    if not self.running then return end
    UIManager:scheduleIn(seconds, self.refresh_task)
end

function SolarDashboard:download()
    local chunks, size = {}, 0
    http.TIMEOUT = 10
    local _, code = http.request{
        url = self.config.url,
        method = "GET",
        redirect = false,
        headers = { Authorization = "Bearer " .. self.config.token, ["Cache-Control"] = "no-cache" },
        create = function()
            local tcp = socket.tcp()
            tcp:settimeout(10)
            return tcp
        end,
        sink = function(chunk)
            if chunk then
                size = size + #chunk
                if size > 2 * 1024 * 1024 then return nil, "Dashboard image is too large" end
                chunks[#chunks + 1] = chunk
            end
            return 1
        end,
    }
    assert(code == 200, "Dashboard server returned " .. tostring(code))
    local body = table.concat(chunks)
    assert(body:sub(1, 8) == png_signature, "Dashboard server did not return a PNG")
    lfs.mkdir(directory)
    local path = directory .. (self.next_slot and "/dashboard-b.png" or "/dashboard-a.png")
    self.next_slot = not self.next_slot
    local file = assert(io.open(path .. ".part", "wb"))
    assert(file:write(body))
    assert(file:close())
    assert(os.rename(path .. ".part", path))
    return path
end

function SolarDashboard:display(path)
    local image = RenderImage:renderImageFile(path, false, Device.screen:getWidth(), Device.screen:getHeight())
    assert(image, "Could not render dashboard image")
    local view = DashboardView:new{ image = image, owner = self }
    local old = self.view
    self.view = view
    UIManager:show(view)
    UIManager:setDirty(view, (self.refresh_count % self.config.full_refresh_every == 0) and "full" or "ui")
    if old then UIManager:close(old) end
    -- Paint now rather than on the next UI tick, so the wait for the next picture starts once this one is up.
    UIManager:forceRePaint()
    self.refresh_count = self.refresh_count + 1
end

function SolarDashboard:noteFailure(message)
    self.failures = self.failures + 1
    -- KOReader's log is kept on the Kindle: note the first failure, then every 100th.
    if self.failures == 1 or self.failures % 100 == 0 then
        logger.warn("Solar dashboard refresh failed (" .. self.failures .. " in a row):", message)
    end
    -- The last picture stays on screen; only explain once when there is nothing to show yet.
    if not self.view and not self.explained then
        self.explained = true
        UIManager:show(InfoMessage:new{ text = "Solar dashboard unavailable.\n\n" .. tostring(message) .. "\n\nRetrying every few seconds.", timeout = 8 })
    end
end

function SolarDashboard:refresh()
    if not self.running or self.refreshing then return end
    if not NetworkMgr:isConnected() then
        -- Wi-Fi dropped: ask the Kindle to rejoin its saved network quietly, then look again shortly.
        NetworkMgr:restoreWifiAsync()
        self:noteFailure("Wi-Fi is not connected")
        self:scheduleNext(math.max(5, self.config.interval))
        return
    end
    self.refreshing = true
    local ok, result = pcall(function() self:display(self:download()) end)
    self.refreshing = false
    if not self.running then return end
    if ok then
        if self.failures > 0 then logger.info("Solar dashboard recovered after", self.failures, "failures") end
        self.failures = 0
        self:scheduleNext(self.config.interval)
    else
        -- The last picture stays up; do not ask an unreachable Pi every second.
        self:noteFailure(result)
        self:scheduleNext(math.max(5, self.config.interval))
    end
end

function SolarDashboard:start()
    if self.running then return end
    local ok, config = pcall(function() return self:loadConfig() end)
    if not ok then
        UIManager:show(InfoMessage:new{ text = tostring(config), timeout = 8 })
        return
    end
    self.config = config
    self.running = true
    self.refreshing = false
    self.refresh_count = 0
    self.failures = 0
    self.explained = false
    self.next_slot = false
    self:setLandscape()
    self:keepAwake()
    self:refresh()
end

function SolarDashboard:stop()
    if not self.running then return end
    self.running = false
    self.refreshing = false
    UIManager:unschedule(self.refresh_task)
    local view = self.view
    self.view = nil
    if view then UIManager:close(view, "full") end
    self:restoreRotation()
    self:restoreSleep()
end

function SolarDashboard:onCloseWidget()
    self:stop()
end

return SolarDashboard
