from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.widget import Widget
from screens.dashboard_screen import BORDER, INK, MUTED, ORANGE

from report_chart_data import CHART_TITLES, axis_caption, axis_ticks


class ReportChart(Widget):
    def __init__(self, buckets, period, on_bar, **kwargs):
        super().__init__(**kwargs)
        self.buckets = buckets
        self.period = period
        self.on_bar = on_bar
        self.bar_targets = []
        self.textures = {}
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def _texture(self, text, size):
        key = (text, size)
        if key not in self.textures:
            label = CoreLabel(text=text, font_size=sp(size))
            label.refresh()
            self.textures[key] = label.texture
        return self.textures[key]

    def _caption(self, text, x, y, *, size=10, align="center"):
        texture = self._texture(text, size)
        offset = {"left": 0, "center": texture.width / 2, "right": texture.width}[align]
        Rectangle(texture=texture, size=texture.size, pos=(x - offset, y - texture.height / 2))

    def _draw(self, *_):
        self.canvas.clear()
        self.bar_targets.clear()
        peak = max((amount for _, _, amount in self.buckets), default=0)
        if not peak:
            with self.canvas:
                Color(*MUTED)
                self._caption("No sales for this period.", self.center_x, self.center_y, size=12)
            return
        ticks = axis_ticks(peak)
        tick_width = max(self._texture(axis_caption(value), 10).width for value in ticks)
        left, right = self.x + tick_width + dp(10), self.right - dp(12)
        bottom, top = self.y + dp(37), self.top - dp(24)
        if right <= left or top <= bottom:
            return
        height = top - bottom
        slot = (right - left) / len(self.buckets)
        last_label_right = self.x
        with self.canvas:
            Color(*MUTED)
            self._caption("Sales (₱)", self.x, self.top - dp(7), align="left")
            self._caption(CHART_TITLES[self.period][1], (left + right) / 2, self.y + dp(7))
            for value in ticks:
                y = bottom + height * value / ticks[-1]
                Color(*BORDER)
                Line(points=(left, y, right, y), width=dp(.6))
                Color(*MUTED)
                self._caption(axis_caption(value), left - dp(5), y, align="right")
            for index, (short, detail, value) in enumerate(self.buckets):
                x = left + slot * (index + .5)
                if value:
                    bar_height = max(dp(1), height * value / ticks[-1])
                    Color(*ORANGE)
                    Rectangle(pos=(x - slot * .32, bottom), size=(slot * .64, bar_height))
                    self.bar_targets.append((x - slot / 2, x + slot / 2, bottom,
                                             bottom + max(dp(16), bar_height), detail, value))
                if self.period == "This Day" and index % 2:
                    continue
                if self.period == "This Month" and index and (index + 1) % 5:
                    continue
                half = self._texture(short, 10).width / 2
                if x - half >= last_label_right and x + half <= self.right:
                    Color(*INK)
                    self._caption(short, x, bottom - dp(11))
                    last_label_right = x + half + dp(7)

    def on_touch_down(self, touch):
        if not touch.is_mouse_scrolling and self.collide_point(*touch.pos):
            for left, right, bottom, top, detail, value in self.bar_targets:
                if left <= touch.x < right and bottom <= touch.y <= top:
                    touch.ud[self] = (touch.pos, detail, value)
                    touch.grab(self)
                    return True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            (x, y), detail, value = touch.ud.pop(self)
            if abs(touch.x - x) <= dp(12) and abs(touch.y - y) <= dp(12):
                self.on_bar(detail, value)
            return True
        return super().on_touch_up(touch)
