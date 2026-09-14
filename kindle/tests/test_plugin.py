"""Run the KOReader plugin in LuaJIT against a simulated KOReader/Kindle environment.

Run from the repo root:  uv run --no-project --with lupa python -m unittest discover -s kindle/tests
"""
import os
from pathlib import Path
import tempfile
import unittest

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    LuaRuntime = None

ROOT = Path(__file__).resolve().parents[1]
PICTURE_DIRECTORY = 'local directory = "/tmp/solar-dashboard"'


@unittest.skipUnless(LuaRuntime, "lupa with LuaJIT 2.1 required")
class SolarPluginTests(unittest.TestCase):
    def run_plugin(self, exercise, status=200, interval=3, full_refresh_every=100):
        lua = LuaRuntime(unpack_returned_tuples=True)
        g = lua.globals()
        g.http_status = status
        g.interval_setting = interval
        g.full_refresh_every_setting = full_refresh_every
        lua.execute(r'''
            clock=1000
            download_seconds=0
            requests=0
            warnings=0
            wifi=true
            connected=true
            local Base = {}
            function Base:extend(t) t=t or {}; t.__index=t; setmetatable(t,{__index=self}); return t end
            function Base:new(t) t=t or {}; setmetatable(t,self); if t.init then t:init() end; return t end
            local screen={
              DEVICE_ROTATED_CLOCKWISE=1,
              rotation=0,
              getWidth=function(self) if self.rotation==1 then return 800 else return 600 end end,
              getHeight=function(self) if self.rotation==1 then return 600 else return 800 end end,
              getRotationMode=function(self) return self.rotation end,
              setRotationMode=function(self,r) self.rotation=r; rotation_changes=(rotation_changes or 0)+1 end,
            }
            device={screen=screen,input={group={Back="Back"}},isKindle=function() return true end}
            uim={
              nextTick=function(_,f) f() end,
              preventStandby=function() prevented=(prevented or 0)+1 end,
              allowStandby=function() prevented=prevented-1 end,
              scheduleIn=function(_,s,f) scheduled=s; scheduled_fn=f end,
              unschedule=function() scheduled=nil end,
              show=function(_,v) shown=v end,
              close=function(_,v) if shown==v then shown=nil end end,
              setDirty=function(_,v,t) refresh_type=t end,
            }
            package.preload["device"]=function() return device end
            package.preload["ui/geometry"]=function() return {new=function(_,t) return t end} end
            package.preload["ui/widget/imagewidget"]=function() return Base end
            package.preload["ui/widget/infomessage"]=function() return Base end
            package.preload["ui/widget/container/inputcontainer"]=function() return Base end
            network={
              isWifiOn=function() return wifi end,
              isConnected=function() return wifi and connected end,
              restoreWifiAsync=function() wifi=true; wifi_restores=(wifi_restores or 0)+1 end,
              turnOffWifi=function() wifi=false end,
            }
            package.preload["ui/network/manager"]=function() return network end
            package.preload["pluginshare"]=function() return {} end
            package.preload["ui/renderimage"]=function() return {renderImageFile=function() return {} end} end
            package.preload["ui/uimanager"]=function() return uim end
            package.preload["ui/widget/container/widgetcontainer"]=function() return Base end
            package.preload["socket.http"]=function() return {request=function(o)
              requests=requests+1
              clock=clock+download_seconds
              if http_status==200 then o.sink(string.char(137).."PNG\r\n"..string.char(26).."\nDATA") end
              return 1,http_status end} end
            package.preload["socket"]=function() return {tcp=function() return {settimeout=function() end} end} end
            package.preload["json"]=function() return {decode=function() return {
              url="http://192.168.0.11:8100/dashboard.png",token=string.rep("a",64),
              interval=interval_setting,full_refresh_every=full_refresh_every_setting} end} end
            package.preload["libs/libkoreader-lfs"]=function() return {
              attributes=function() return nil end,mkdir=function() return true end} end
            package.preload["logger"]=function() return {warn=function() warnings=warnings+1 end,info=function() end} end
            os.time=function() return clock end
            os.execute=function(c) last_command=c; commands=(commands or "")..c.."\n"; return 0 end
            -- Windows cannot rename over an existing file; the Kindle (Linux) can.
            local real_rename=os.rename
            os.rename=function(from,to) os.remove(to); return real_rename(from,to) end
        ''')
        source = (ROOT / "koreader/plugins/solardashboard.koplugin/main.lua").read_text(encoding="utf-8")
        self.assertIn(PICTURE_DIRECTORY, source)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            (temp_path / "settings").mkdir()
            (temp_path / "settings" / "solar-dashboard.json").write_text("{}")
            (temp_path / "solar").mkdir()
            source = source.replace(PICTURE_DIRECTORY, f'local directory = "{(temp_path / "solar").as_posix()}"')
            previous = os.getcwd()
            try:
                os.chdir(temp_path)
                plugin = lua.execute(source)
                plugin.ui = lua.table_from({"menu": lua.table_from({"registerToMainMenu": lambda *args: None})})
                plugin.init(plugin)
                plugin.start(plugin)
                exercise(plugin, lua)
            finally:
                os.chdir(previous)

    def test_start_keeps_awake_shows_picture_and_schedules_next_refresh(self):
        def exercise(plugin, lua):
            g = lua.globals()
            self.assertTrue(plugin.running)
            self.assertEqual(g.scheduled, 3)
            self.assertEqual(g.prevented, 1)
            self.assertEqual(g.refresh_type, "full")
            self.assertEqual(g.device.screen.rotation, 1)
            self.assertIn("preventScreenSaver 1", g.last_command)
            plugin.stop(plugin)
            self.assertFalse(plugin.running)
            self.assertEqual(g.prevented, 0)
            self.assertIn("preventScreenSaver 0", g.last_command)
            self.assertEqual(g.device.screen.rotation, 0)
            self.assertEqual(g.rotation_changes, 2)
        self.run_plugin(exercise)

    def test_keeps_refreshing_with_partial_updates_and_a_periodic_full_refresh(self):
        def exercise(plugin, lua):
            g = lua.globals()
            refresh_types = [g.refresh_type]
            for _ in range(3):
                g.scheduled_fn()
                refresh_types.append(g.refresh_type)
            self.assertEqual(refresh_types, ["full", "ui", "ui", "full"])
            self.assertEqual((plugin.refresh_count, g.requests), (4, 4))
            plugin.stop(plugin)
        self.run_plugin(exercise, full_refresh_every=3)

    def test_never_turns_wifi_off_or_suspends(self):
        def exercise(plugin, lua):
            g = lua.globals()
            for _ in range(5):
                g.scheduled_fn()
            plugin.stop(plugin)
            self.assertTrue(g.wifi)
            self.assertNotIn("suspend", g.commands)
        self.run_plugin(exercise)

    def test_cadence_is_measured_from_the_start_of_each_fetch(self):
        def exercise(plugin, lua):
            g = lua.globals()
            g.download_seconds = 2
            g.scheduled_fn()
            self.assertEqual(g.scheduled, 1)
            g.download_seconds = 5
            g.scheduled_fn()
            self.assertEqual(g.scheduled, 1)  # a slow download never turns into a busy loop
            plugin.stop(plugin)
        self.run_plugin(exercise)

    def test_failure_keeps_the_last_picture_and_retries(self):
        def exercise(plugin, lua):
            g = lua.globals()
            g.picture = plugin.view
            g.http_status = 503
            g.scheduled_fn()
            self.assertTrue(plugin.running)
            self.assertTrue(lua.eval("shown == picture"))
            self.assertEqual(g.scheduled, 3)
            plugin.stop(plugin)
        self.run_plugin(exercise)

    def test_failure_before_any_picture_explains_once_and_keeps_retrying(self):
        def exercise(plugin, lua):
            g = lua.globals()
            self.assertTrue(plugin.running)
            self.assertIn("unavailable", g.shown.text)
            self.assertEqual(g.scheduled, 3)
            g.shown = None
            g.scheduled_fn()
            self.assertIsNone(g.shown)  # not repeated every few seconds
            self.assertEqual(g.warnings, 1)  # and the Kindle's log is not flooded
            g.http_status = 200
            g.scheduled_fn()
            self.assertIsNotNone(plugin.view)
            plugin.stop(plugin)
        self.run_plugin(exercise, status=503)

    def test_lost_wifi_reconnects_quietly_without_stopping(self):
        def exercise(plugin, lua):
            g = lua.globals()
            g.connected = False
            g.scheduled_fn()
            self.assertEqual((g.wifi_restores, g.requests, g.scheduled), (1, 1, 5))
            self.assertTrue(plugin.running)
            g.connected = True
            g.scheduled_fn()
            self.assertEqual(g.requests, 2)
            plugin.stop(plugin)
        self.run_plugin(exercise)

    def test_rejects_an_interval_below_one_second(self):
        def exercise(plugin, lua):
            self.assertFalse(plugin.running)
            self.assertIn("at least 1 second", lua.globals().shown.text)
        self.run_plugin(exercise, interval=0.5)


if __name__ == "__main__":
    unittest.main()
