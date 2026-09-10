"""
Central registry of every non-ASCII symbol (emoji, box-drawing arrows,
bullets, etc.) used anywhere in Mesh's terminal output.

Every symbol used across the codebase is defined here exactly once as a
module-level ``Glyph`` instance. Other modules import the specific glyphs
they need (e.g. ``from glyphs import CHECK, BULLET``) and use them directly
inside f-strings - the glyph itself decides, at print time, whether to
render its normal Unicode form or a plain-ASCII fallback.

Unicode terminals get the normal symbols. Terminals that can't render
Unicode (or users who simply prefer plain text) can pass ``--ascii`` on the
command line, which calls :func:`set_ascii_mode` before anything is
printed. From that point on every ``Glyph`` renders its ``ascii`` fallback
instead of its Unicode form.

Call :func:`set_ascii_mode` as early as possible (before any output is
produced) since a ``Glyph``'s rendering is decided fresh every time it is
converted to a string.

NOTE ON FALLBACK SPELLING: almost all of Mesh's output goes through Rich's
``console.print(...)``, which parses ``[style]...[/style]`` markup in
whatever string it's given. Square brackets in an ASCII fallback (e.g.
``"[OK]"``) would therefore be silently swallowed by Rich's markup parser
instead of being printed. Every fallback below is written with parentheses
or other markup-safe punctuation instead of square brackets for this
reason - keep that in mind if you add a new glyph.
"""

# Set to True by main.py when the --ascii CLI switch is passed.
ASCII_MODE = False


def set_ascii_mode(enabled: bool) -> None:
    """Enable or disable ASCII-only rendering for every glyph in this module."""
    global ASCII_MODE
    ASCII_MODE = enabled


def is_ascii_mode() -> bool:
    return ASCII_MODE


class Glyph:
    """A symbol with a Unicode form and a plain-ASCII fallback.

    Behaves like a string in f-strings and str.format() calls: it renders
    as ``unicode`` normally, or as ``ascii`` when ASCII mode is enabled.
    """

    __slots__ = ("unicode", "ascii")

    def __init__(self, unicode: str, ascii: str):
        self.unicode = unicode
        self.ascii = ascii

    def __str__(self) -> str:
        return self.ascii if ASCII_MODE else self.unicode

    def __format__(self, spec: str) -> str:
        return format(str(self), spec)

    def __repr__(self) -> str:
        return f"Glyph({self.unicode!r}, {self.ascii!r})"

    def __eq__(self, other) -> bool:
        if isinstance(other, Glyph):
            return self.unicode == other.unicode and self.ascii == other.ascii
        return str(self) == other

    def __hash__(self):
        return hash((self.unicode, self.ascii))

    def __add__(self, other):
        return str(self) + str(other)

    def __radd__(self, other):
        return str(other) + str(self)

    def __len__(self):
        return len(str(self))


# --- Punctuation / layout -------------------------------------------------
BULLET = Glyph("•", "*")
EM_DASH = Glyph("—", "--")
EN_DASH = Glyph("–", "-")
VS16 = Glyph("\uFE0F", "")  # emoji variation selector, invisible either way

# --- Status / result markers ----------------------------------------------
CHECK = Glyph("✔", "(OK)")
CHECK_BOX = Glyph("✅", "(OK)")
CROSS = Glyph("✖", "x")
NO_ENTRY = Glyph("⛔", "(X)")
WARNING = Glyph("⚠", "(!)")
BLOCKED = Glyph("⊘", "(skip)")
QUESTION = Glyph("❓", "?")

# --- Navigation / direction ------------------------------------------------
PLAY = Glyph("▶", ">")
SMALL_TRIANGLE_RIGHT = Glyph("▸", ">")
TRIANGLE_UP = Glyph("▲", "^")
TRIANGLE_DOWN = Glyph("▼", "v")
ARROW_UP = Glyph("↑", "^")
ARROW_DOWN = Glyph("↓", "v")
ARROW_TIP_RIGHT = Glyph("↳", "->")
ANGLE_RIGHT = Glyph("❯", ">")
RADIO_ON = Glyph("🔘", "(*)")
RADIO_OFF = Glyph("⚪", "( )")
CIRCLE_OPEN = Glyph("○", "o")

# --- Actions / tools ---------------------------------------------------
LIGHTNING = Glyph("⚡", "(!)")
SHUFFLE = Glyph("🔀", "(shuffle)")
WRENCH = Glyph("🔧", "(tool)")
HAMMER_WRENCH = Glyph("🛠", "(tools)")
REFRESH = Glyph("🔄", "(refresh)")
ROCKET = Glyph("🚀", "(launch)")
SCALES = Glyph("⚖", "(balance)")
SHIELD = Glyph("🛡", "(guard)")
BANDAGE = Glyph("🩹", "(fix)")
MAG_LEFT = Glyph("🔍", "(search)")
MAG_RIGHT = Glyph("🔎", "(find)")

# --- People / agents ---------------------------------------------------
BRAIN = Glyph("🧠", "(AI)")
ROBOT = Glyph("🤖", "(BOT)")
PEOPLE = Glyph("👥", "(team)")
PERSON = Glyph("👤", "(user)")

# --- Misc symbols / emoji ------------------------------------------------
INFO = Glyph("ℹ", "(i)")
TREE = Glyph("🌳", "(tree)")
HOURGLASS = Glyph("⏳", "(wait)")
OUTBOX = Glyph("📤", "(out)")
SCROLL = Glyph("📜", "(log)")
TABS = Glyph("📑", "(tabs)")
PAPERCLIP = Glyph("📎", "(attach)")
PARTY = Glyph("🎉", "(done)")
CHAT = Glyph("💬", "(chat)")
SNAKE = Glyph("🐍", "(py)")
POSTBOX = Glyph("📮", "(post)")
SLEEP = Glyph("💤", "(idle)")
MEMO = Glyph("📝", "(note)")
