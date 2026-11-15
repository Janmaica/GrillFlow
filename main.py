from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager
from kivy.utils import platform

from screens.splash_screen import LoginScreen, SplashScreen


class GrillFlowApp(App):
    def build(self):
        self.title = "GrillFlow"
        manager = ScreenManager()
        manager.add_widget(SplashScreen(name="splash"))
        manager.add_widget(LoginScreen(name="login"))
        return manager


if __name__ == "__main__":
    if platform != "android":
        Window.size = (400, 750)
    Window.clearcolor = (23 / 255, 17 / 255, 14 / 255, 1)
    GrillFlowApp().run()
