"""Chat-box dialogs: continuing through "Click here to continue" and picking numbered
options with the keyboard. Detection is by the continue prompt's blue text."""
from .vision import color_mask

CONTINUE_BLUE = (0, 0, 255)


class Dialog:
    def __init__(self, game, continue_color=CONTINUE_BLUE, tolerance: int = 40):
        self.game = game
        self.color = continue_color
        self.tolerance = tolerance

    def waiting(self, img) -> bool:
        """Is a "Click here to continue" prompt showing?"""
        box = self.game.layout.chatbox.crop(img)
        return int(color_mask(box, self.color, self.tolerance).sum()) >= 20

    def advance(self, limit: int = 20) -> int:
        """Press space through every "continue" page. Returns how many were skipped."""
        g, n = self.game, 0
        while n < limit and self.waiting(g.grab()):
            g.controls.press("space")
            g.wait(0.6, 1.0)
            n += 1
        return n

    def choose(self, option: int) -> None:
        """Pick a numbered chat option (1-5) by its number key."""
        self.game.controls.press(str(option))
        self.game.wait(0.6, 1.0)

    def talk(self, options=()) -> None:
        """Continue, then answer each option in turn, continuing after each."""
        self.advance()
        for option in options:
            self.choose(option)
            self.advance()
