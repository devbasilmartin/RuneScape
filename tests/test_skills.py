from skillbot.skills import LEVEL_COLOR, SKILLS, SkillReader

from fakes import LAYOUT, blank

FONT = {
    "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
}


def draw_level(img, skill, level):
    box = LAYOUT.skill_level(SKILLS.index(skill))
    img[box.y:box.y + box.h, box.x:box.x + box.w] = (60, 50, 40)
    x = box.x + 2
    for d in str(level):
        for r, row in enumerate(FONT[d]):
            for c, bit in enumerate(row):
                if bit == "1":
                    img[box.y + 4 + r, x + c] = LEVEL_COLOR
                    img[box.y + 5 + r, x + c + 1] = (0, 0, 0)   # drop shadow
        x += 4


def skills_tab(levels):
    img = blank()
    for skill, level in levels.items():
        draw_level(img, skill, level)
    return img


def test_learn_then_read():
    reader = SkillReader(LAYOUT)
    img = skills_tab({"attack": 1, "hitpoints": 10, "fishing": 23})
    for skill, level in (("attack", 1), ("hitpoints", 10), ("fishing", 23)):
        assert reader.learn(img, skill, level)
    assert reader.known_digits() == "0123"
    assert reader.read(img, "fishing") == 23
    img2 = skills_tab({"mining": 32, "cooking": 5})
    assert reader.read(img2, "mining") == 32
    assert reader.read(img2, "cooking") is None     # 5 not learned yet


def test_learns_new_digit_when_level_ticks_up_by_one():
    reader = SkillReader(LAYOUT)
    reader.learn(skills_tab({"hitpoints": 10}), "hitpoints", 10)
    assert reader.read_expecting(skills_tab({"woodcutting": 2}), "woodcutting", 1) == 2
    assert reader.read_expecting(skills_tab({"woodcutting": 3}), "woodcutting", 2) == 3
    assert reader.known_digits() == "0123"
    # a known level still reads normally
    assert reader.read_expecting(skills_tab({"woodcutting": 3}), "woodcutting", 3) == 3


def test_refuses_to_guess_when_ambiguous():
    reader = SkillReader(LAYOUT)
    reader.learn(skills_tab({"hitpoints": 10}), "hitpoints", 10)
    assert reader.read_expecting(skills_tab({"woodcutting": 4}), "woodcutting", 1, max_jump=3) is None
    assert reader.known_digits() == "01"


def test_digits_saved_and_loaded(tmp_path):
    reader = SkillReader.load(LAYOUT, tmp_path)
    reader.learn(skills_tab({"attack": 12}), "attack", 12)
    reader.save()
    again = SkillReader.load(LAYOUT, tmp_path)
    assert again.read(skills_tab({"magic": 21}), "magic") == 21
