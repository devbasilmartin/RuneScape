"""Fixed-mode client geometry, in pixels relative to the top-left of the game canvas.

Fixed mode is always 765x503, so every UI element sits at a known offset from the
canvas origin. The defaults are best guesses: check them with
``python -m skillbot debug`` and override any of them in config.yaml under ``layout:``.
"""
from dataclasses import dataclass, field, fields


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def crop(self, img):
        return img[self.y:self.y + self.h, self.x:self.x + self.w]

    def grow(self, n: int) -> "Rect":
        return Rect(self.x - n, self.y - n, self.w + 2 * n, self.h + 2 * n)


CANVAS_W, CANVAS_H = 765, 503


@dataclass
class Layout:
    viewport: Rect = field(default_factory=lambda: Rect(4, 4, 512, 334))
    compass: tuple[int, int] = (561, 20)
    run_orb: tuple[int, int] = (557, 129)    # centre of the boot icon next to the minimap
    minimap_center: tuple[int, int] = (643, 84)
    minimap_radius: int = 70
    world_map_button: tuple[int, int] = (720, 140)   # the world map orb by the minimap
    world_map_center: tuple[int, int] = (260, 170)   # where the map centres on the player
    # right-click menus: header height, then one row per option
    menu_header: int = 19
    menu_row: int = 15
    # chat box, for "Click here to continue" and numbered options
    chatbox: Rect = field(default_factory=lambda: Rect(7, 345, 499, 130))
    run_energy_box: Rect = field(default_factory=lambda: Rect(519, 122, 24, 12))  # the number

    # inventory: 4 columns x 7 rows
    inv_origin: tuple[int, int] = (563, 213)
    slot_step: tuple[int, int] = (42, 36)
    slot_size: tuple[int, int] = (32, 32)

    # side panel tab buttons
    tabs: dict = field(default_factory=lambda: {
        "combat": (538, 186), "skills": (571, 186), "inventory": (637, 186),
        "magic": (736, 186)})

    # combat options tab: the four attack style buttons, in game order
    combat_styles: tuple = ((603, 270), (683, 270), (603, 322), (683, 322))

    # RuneLite Status Bars plugin: the health bar beside the inventory
    hp_bar: Rect = field(default_factory=lambda: Rect(547, 212, 8, 250))

    # skills tab: 3 columns x 8 rows; level_box is where the base level is drawn in a cell
    skill_origin: tuple[int, int] = (550, 210)
    skill_step: tuple[int, int] = (63, 32)
    skill_level_box: tuple[int, int, int, int] = (36, 15, 24, 13)

    # bank interface item grid (8 columns)
    bank_origin: tuple[int, int] = (73, 83)
    bank_step: tuple[int, int] = (48, 36)
    bank_columns: int = 8
    bank_search: tuple[int, int] = (461, 318)
    bank_quantity: dict = field(default_factory=lambda: {
        "1": (198, 318), "5": (223, 318), "10": (248, 318), "x": (273, 318), "all": (298, 318)})

    # login screen buttons
    login_existing_user: tuple[int, int] = (462, 291)
    login_play: tuple[int, int] = (383, 324)

    # points on the side-panel frame, sampled to tell "logged in" from the login screen
    fingerprint_points: tuple = ((530, 215), (530, 330), (530, 450), (752, 215),
                                 (752, 330), (752, 450), (640, 170), (640, 480))

    def slot(self, i: int) -> Rect:
        col, row = i % 4, i // 4
        return Rect(self.inv_origin[0] + col * self.slot_step[0],
                    self.inv_origin[1] + row * self.slot_step[1], *self.slot_size)

    @property
    def inventory(self) -> Rect:
        last = self.slot(27)
        return Rect(self.inv_origin[0], self.inv_origin[1],
                    last.x + last.w - self.inv_origin[0], last.y + last.h - self.inv_origin[1])

    def skill_cell(self, index: int) -> Rect:
        col, row = index % 3, index // 3
        return Rect(self.skill_origin[0] + col * self.skill_step[0],
                    self.skill_origin[1] + row * self.skill_step[1], *self.skill_step)

    def skill_level(self, index: int) -> Rect:
        cell = self.skill_cell(index)
        dx, dy, w, h = self.skill_level_box
        return Rect(cell.x + dx, cell.y + dy, w, h)

    def bank_slot(self, i: int) -> Rect:
        col, row = i % self.bank_columns, i // self.bank_columns
        return Rect(self.bank_origin[0] + col * self.bank_step[0],
                    self.bank_origin[1] + row * self.bank_step[1], *self.slot_size)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Layout":
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        for key, value in list(d.items()):
            if key not in names:
                raise ValueError(f"unknown layout key: {key}")
            if key in ("viewport", "hp_bar", "run_energy_box", "chatbox"):
                d[key] = Rect(*value)
            elif key in ("tabs", "bank_quantity"):
                d[key] = {**getattr(cls(), key), **{str(k): tuple(v) for k, v in value.items()}}
            elif key in ("fingerprint_points", "combat_styles"):
                d[key] = tuple(tuple(p) for p in value)
            elif isinstance(value, list):
                d[key] = tuple(value)
        return cls(**d)
