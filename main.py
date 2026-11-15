
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.core.window import Window

# GrillFlow orange theme
ORANGE = (0.918, 0.345, 0.047, 1)
CREAM = (1, 0.969, 0.929, 1)

Window.size = (400, 750)
Window.clearcolor = CREAM


class GrillFlowApp(App):
    def build(self):
        self.title = "GrillFlow"

        layout = BoxLayout(
            orientation="vertical",
            padding=20,
            spacing=15
        )

        title = Label(
            text="[b]GrillFlow[/b]",
            markup=True,
            font_size=36,
            color=ORANGE,
            size_hint_y=0.25
        )

        subtitle = Label(
            text="BBQ Business Management System",
            font_size=17,
            color=(0.45, 0.25, 0.12, 1),
            size_hint_y=0.15
        )

        dashboard_button = Button(
            text="Open Dashboard",
            font_size=18,
            background_normal="",
            background_color=ORANGE,
            size_hint_y=None,
            height=55
        )

        dashboard_button.bind(
            on_press=self.open_dashboard
        )

        layout.add_widget(title)
        layout.add_widget(subtitle)
        layout.add_widget(dashboard_button)

        return layout

    def open_dashboard(self, instance):
        instance.text = "Dashboard Coming Soon!"


if __name__ == "__main__":
    GrillFlowApp().run()
