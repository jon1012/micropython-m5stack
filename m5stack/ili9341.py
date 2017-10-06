import time
import ustruct
import framebuf

_COLUMN_SET = const(0x2a)
_PAGE_SET = const(0x2b)
_RAM_WRITE = const(0x2c)
_RAM_READ = const(0x2e)
_DISPLAY_ON = const(0x29)
_WAKE = const(0x11)
_LINE_SET = const(0x37)
_MADCTL = const(0x36)

_MADCTL_MY = const(0x80)
_MADCTL_MX = const(0x40)
_MADCTL_MV = const(0x20)
_MADCTL_ML = const(0x10)
_MADCTL_RGB = const(0x00)
_MADCTL_BGR = const(0x08)
_MADCTL_MH = const(0x04)


def color565(r, g, b):
    return (r & 0xf8) << 8 | (g & 0xfc) << 3 | b >> 3


def get_m5_display():
    from machine import Pin, SPI
    Pin(32, Pin.OUT).value(1)  # lcd on
    spi = SPI(miso=Pin(19), mosi=Pin(23, Pin.OUT), sck=Pin(18, Pin.OUT),
              spihost=SPI.VSPI, baudrate=40000000)
    display = ILI9341(spi, cs=Pin(14, Pin.OUT), dc=Pin(27, Pin.OUT),
                      rst=Pin(33, Pin.OUT))
    return display


class ILI9341:
    """
    A simple driver for the ILI9341/ILI9340-based displays.


    >>> import ili9341
    >>> from machine import Pin, SPI
    >>> spi = SPI(miso=Pin(12), mosi=Pin(13, Pin.OUT), sck=Pin(14, Pin.OUT))
    >>> display = ili9341.ILI9341(spi, cs=Pin(0), dc=Pin(5), rst=Pin(4))
    >>> display.fill(ili9341.color565(0xff, 0x11, 0x22))
    >>> display.pixel(120, 160, 0)
    """

    width = 320
    height = 240

    def __init__(self, spi, cs, dc, rst, rotation=0, mode=_MADCTL_BGR):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.mode = mode
        self.cs.init(self.cs.OUT, value=1)
        self.dc.init(self.dc.OUT, value=0)
        self.rst.init(self.rst.OUT, value=0)
        self.reset()
        self.init()
        time.sleep_ms(120)
        self.set_rotation(rotation)
        self._scroll = 0

    def init(self):
        for command, data in (
            (0xef, b'\x03\x80\x02'),
            (0xcf, b'\x00\xc1\x30'),
            (0xed, b'\x64\x03\x12\x81'),
            (0xe8, b'\x85\x00\x78'),
            (0xcb, b'\x39\x2c\x00\x34\x02'),
            (0xf7, b'\x20'),
            (0xea, b'\x00\x00'),
            (0xc0, b'\x23'),  # Power Control 1, VRH[5:0]
            (0xc1, b'\x10'),  # Power Control 2, SAP[2:0], BT[3:0]
            (0xc5, b'\x3e\x28'),  # VCM Control 1
            (0xc7, b'\x86'),  # VCM Control 2
            (0x36, b'\x48'),  # Memory Access Control
            (0x36, b'\x40'),  # Memory Access Control
            (0x3a, b'\x55'),  # Pixel Format
            (0xb1, b'\x00\x18'),  # FRMCTR1
            (0xb6, b'\x08\x82\x27'),  # Display Function Control
            (0xf2, b'\x00'),  # 3Gamma Function Disable
            (0x26, b'\x01'),  # Gamma Curve Selected
            (0xe0,  # Set Gamma
             b'\x0f\x31\x2b\x0c\x0e\x08\x4e\xf1\x37\x07\x10\x03\x0e\x09\x00'),
            (0xe1,  # Set Gamma
             b'\x00\x0e\x14\x03\x11\x07\x31\xc1\x48\x08\x0f\x0c\x31\x36\x0f'),
        ):
            self._write(command, data)
        self._write(_WAKE)
        time.sleep_ms(120)
        self._write(_DISPLAY_ON)

    def reset(self):
        self.rst.value(0)
        time.sleep_ms(50)
        self.rst.value(1)
        time.sleep_ms(50)

    def _write(self, command, data=None):
        self.dc.value(0)
        self.cs.value(0)
        self.spi.write(bytearray([command]))
        self.cs.value(1)
        if data is not None:
            self._data(data)

    def _data(self, data):
        self.dc.value(1)
        self.cs.value(0)
        self.spi.write(data)
        self.cs.value(1)

    def set_rotation(self, value):
        values = [_MADCTL_MX | self.mode,
                  _MADCTL_MV | self.mode,
                  _MADCTL_MY | self.mode,
                  _MADCTL_MX | _MADCTL_MY | _MADCTL_MV | self.mode]
        self._write(_MADCTL, ustruct.pack(">H", values[value % 4]))

    def _block(self, x0, y0, x1, y1, data=None):
        self._write(_COLUMN_SET, ustruct.pack(">HH", x0, x1))
        self._write(_PAGE_SET, ustruct.pack(">HH", y0, y1))
        if data is None:
            return self._read(_RAM_READ, (x1 - x0 + 1) * (y1 - y0 + 1) * 3)
        self._write(_RAM_WRITE, data)

    def _read(self, command, count):
        self.dc.value(0)
        self.cs.value(0)
        self.spi.write(bytearray([command]))
        data = self.spi.read(count)
        self.cs.value(1)
        return data

    def pixel(self, x, y, color=None):
        if color is None:
            r, b, g = self._block(x, y, x, y)
            return color565(r, g, b)
        if not 0 <= x < self.width or not 0 <= y < self.height:
            return
        self._block(x, y, x, y, ustruct.pack(">H", color))

    def fill_rectangle(self, x, y, w, h, color):
        x = min(self.width - 1, max(0, x))
        y = min(self.height - 1, max(0, y))
        w = min(self.width - x, max(1, w))
        h = min(self.height - y, max(1, h))
        self._block(x, y, x + w - 1, y + h - 1, b'')
        chunks, rest = divmod(w * h, 512)
        if chunks:
            data = ustruct.pack(">H", color) * 512
            for count in range(chunks):
                self._data(data)
        data = ustruct.pack(">H", color) * rest
        self._data(data)

    def fill(self, color):
        self.fill_rectangle(0, 0, self.width, self.height, color)

    def char(self, char, x, y, color=0xffff, background=0x0000):
        buffer = bytearray(8)
        framebuffer = framebuf.FrameBuffer1(buffer, 8, 8)
        framebuffer.text(char, 0, 0)
        color = ustruct.pack(">H", color)
        background = ustruct.pack(">H", background)
        data = bytearray(2 * 8 * 8)
        for c, byte in enumerate(buffer):
            for r in range(8):
                if byte & (1 << r):
                    data[r * 8 * 2 + c * 2] = color[0]
                    data[r * 8 * 2 + c * 2 + 1] = color[1]
                else:
                    data[r * 8 * 2 + c * 2] = background[0]
                    data[r * 8 * 2 + c * 2 + 1] = background[1]
        self._block(x, y, x + 7, y + 7, data)

    def font_char(self, font, char, x, y, color=0xffff, background=0x0000):
        glyph, char_height, char_width = font.get_ch(char)
        div, mod = divmod(char_height, 8)
        color = ustruct.pack(">H", color)
        background = ustruct.pack(">H", background)
        gbytes = div + 1 if mod else div    # No. of bytes per column of glyph
        odata = bytearray(2 * char_height * char_width)
        for scol in range(char_width):      # Source column)
            for srow in range(char_height): # Source row
                gbyte, gbit = divmod(srow, 8)
                if gbit == 0:               # Next glyph byte
                    data = glyph[scol * gbytes + gbyte]
                if data & (1 << gbit):
                    odata[srow * char_width * 2 + scol * 2] = color[0]
                    odata[srow * char_width * 2 + scol * 2 + 1] = color[1]
                else:
                    odata[srow * char_width * 2 + scol * 2] = background[0]
                    odata[srow * char_width * 2 + scol * 2 + 1] = background[1]
        self._block(x, y, x + char_width - 1, y + char_height - 1, odata)

        return char_width # we tell the last char width

    def text(self, text, x, y, color=0xffff, background=0x0000, wrap=None,
             vwrap=None, clear_eol=False, font=None):
        if wrap is None:
            wrap = self.width - 8
        if vwrap is None:
            vwrap = self.height - 8
        tx = x
        ty = y

        def new_line():
            # TODO: handle font size
            nonlocal tx, ty

            tx = x
            ty += 8
            if ty >= vwrap:
                ty = y

        for char in text:
            if char == '\n':
                if clear_eol and tx < wrap:
                    # TODO: handle font size
                    self.fill_rectangle(tx, ty, wrap - tx + 7, 8, background)
                new_line()
            else:
                if tx >= wrap:
                    new_line()
                if font is None:
                    self.char(char, tx, ty, color, background)
                    tx += 8
                else:
                    tx += self.font_char(font, char, tx, ty, color, background)
        if clear_eol and tx < wrap:
            # TODO: handle font size
            self.fill_rectangle(tx, ty, wrap - tx + 7, 8, background)

    def scroll(self, dy=None):
        if dy is None:
            return self._scroll
        self._scroll = (self._scroll + dy) % self.height
        self._write(_LINE_SET, ustruct.pack('>H', self._scroll))
