import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw, ImageFont, ImageWin, ImageTk
import barcode
from barcode.writer import ImageWriter
import win32print, win32ui, win32con
import io, os, json, traceback, sys, re
from datetime import datetime

CONFIG_PATH  = os.path.join(os.path.expanduser("~"), ".barcode_xp365b.json")
LOG_PATH     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")
BASE_DPI     = 203
MARGIN_MM    = 1.0
TEXT_H_MM    = 4.5
TOP_TEXT_MM  = 4.0

PRESETS = [
    ("30 × 20 мм", 30.0, 20.0),
    ("35 × 25 мм", 35.0, 25.0),
    ("40 × 20 мм", 40.0, 20.0),
    ("40 × 30 мм", 40.0, 30.0),
    ("50 × 30 мм", 50.0, 30.0),
    ("58 × 40 мм", 58.0, 40.0),
    ("60 × 40 мм", 60.0, 40.0),
    ("70 × 40 мм", 70.0, 40.0),
    ("Свой размер…", 0, 0),
]


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


def mm2px(mm, dpi=BASE_DPI):
    return int(round(mm / 25.4 * dpi))


def build_sequence(start_str, count):
    """Возвращает список значений для печати.
    - если в конце есть цифры → инкрементим их (сохраняя ширину: 001 → 002)
    - если цифр нет вообще → тот же текст count раз
    """
    start_str = start_str.strip()
    m = re.search(r'(\d+)$', start_str)
    if not m:
        return [start_str] * count

    prefix = start_str[:m.start()]
    num    = int(m.group(1))
    width  = len(m.group(1))

    out = []
    for i in range(count):
        v = num + i
        s = f"{v:0{width}d}" if len(str(v)) <= width else str(v)
        out.append(prefix + s)
    return out


def _load_font(size_px):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size_px)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_centered(draw, text, top, height, font, img_width):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (img_width - tw) // 2 - bbox[0]
    ty = top + (height - th) // 2 - bbox[1]
    draw.text((tx, ty), text, fill="black", font=font)


def make_label(code, label_w_mm, label_h_mm, top_text=None):
    W_px = mm2px(label_w_mm)
    H_px = mm2px(label_h_mm)
    margin_px = mm2px(MARGIN_MM)
    num_h_px  = mm2px(TEXT_H_MM)
    top_h_px  = mm2px(TOP_TEXT_MM) if top_text else 0

    img = Image.new("RGB", (W_px, H_px), "white")

    bc_area_w = W_px - 2 * margin_px
    bc_area_h = H_px - 2 * margin_px - num_h_px - top_h_px
    if bc_area_w <= 0 or bc_area_h <= 0:
        return img

    # текст сверху
    if top_text:
        draw = ImageDraw.Draw(img)
        font = _load_font(max(8, int(top_h_px * 0.75)))
        _draw_centered(draw, top_text, margin_px, top_h_px, font, W_px)

    # штрихкод Code128 (сам подберёт режим: Code C для цифр, A/B для текста)
    CODE128 = barcode.get_barcode_class('code128')
    bc = CODE128(code, writer=ImageWriter())
    opts = {
        'module_width':  0.2,
        'module_height': bc_area_h / BASE_DPI * 25.4,
        'quiet_zone':    0,
        'write_text':    False,
        'dpi':           BASE_DPI,
        'center_text':   False,
    }
    rendered = bc.render(opts)
    if isinstance(rendered, (bytes, bytearray)):
        bc_img = Image.open(io.BytesIO(rendered)).convert("RGB")
    else:
        bc_img = rendered.convert("RGB")

    bc_img = bc_img.resize((bc_area_w, bc_area_h), Image.LANCZOS)
    img.paste(bc_img, (margin_px, margin_px + top_h_px))

    # номер снизу
    draw = ImageDraw.Draw(img)
    font = _load_font(max(8, int(num_h_px * 0.75)))
    _draw_centered(draw, code, H_px - margin_px - num_h_px, num_h_px, font, W_px)

    return img


def print_labels(printer_name, codes, label_w_mm, label_h_mm,
                 rotate180=False, top_text=None):
    hDC = win32ui.CreateDC()
    hDC.CreatePrinterDC(printer_name)

    dpi_x = hDC.GetDeviceCaps(win32con.LOGPIXELSX)
    dpi_y = hDC.GetDeviceCaps(win32con.LOGPIXELSY)
    target_w = int(round(label_w_mm / 25.4 * dpi_x))
    target_h = int(round(label_h_mm / 25.4 * dpi_y))

    hDC.StartDoc("Barcodes")
    try:
        for code in codes:
            img = make_label(code, label_w_mm, label_h_mm, top_text)
            if rotate180:
                img = img.rotate(180)
            hDC.StartPage()
            dib = ImageWin.Dib(img)
            dib.draw(hDC.GetHandleOutput(), (0, 0, target_w, target_h))
            hDC.EndPage()
    finally:
        hDC.EndDoc()
        hDC.DeleteDC()


def list_printers():
    return [p[2] for p in win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Печать штрихкодов XP-365B")
        self.geometry("860x470")
        self.resizable(False, False)

        cfg = load_config()

        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        left = ttk.Frame(main, padding=(0, 0, 12, 0))
        left.grid(row=0, column=0, sticky="nw")

        right = ttk.Frame(main, padding=6, relief="solid", borderwidth=1)
        right.grid(row=0, column=1, sticky="nsew")

        # --- принтер ---
        ttk.Label(left, text="Принтер:").grid(row=0, column=0, sticky="w", pady=5)
        self.printer_var = tk.StringVar()
        printers = list_printers()
        ttk.Combobox(left, textvariable=self.printer_var, values=printers,
                     width=36, state="readonly").grid(row=0, column=1, pady=5, sticky="we")

        saved_printer = cfg.get("printer")
        if saved_printer in printers:
            self.printer_var.set(saved_printer)
        else:
            for p in printers:
                if "365" in p or "xprinter" in p.lower():
                    self.printer_var.set(p)
                    break
            else:
                if printers:
                    self.printer_var.set(printers[0])

        # --- размер ---
        ttk.Label(left, text="Размер этикетки:").grid(row=1, column=0, sticky="w", pady=5)
        self.size_var = tk.StringVar()
        self.size_combo = ttk.Combobox(left, textvariable=self.size_var,
                                       values=[p[0] for p in PRESETS],
                                       width=34, state="readonly")
        self.size_combo.grid(row=1, column=1, pady=5, sticky="we")
        self.size_combo.bind("<<ComboboxSelected>>", self.on_size_change)

        saved_size = cfg.get("size_name")
        if saved_size in [p[0] for p in PRESETS]:
            self.size_var.set(saved_size)
        else:
            self.size_var.set(PRESETS[0][0])

        self.w_var = tk.StringVar(value=str(cfg.get("custom_w", 30)))
        self.h_var = tk.StringVar(value=str(cfg.get("custom_h", 20)))

        ttk.Label(left, text="Ш × В (мм):").grid(row=2, column=0, sticky="w", pady=5)
        cframe = ttk.Frame(left)
        cframe.grid(row=2, column=1, sticky="w", pady=5)
        self.w_entry = ttk.Entry(cframe, textvariable=self.w_var, width=8)
        self.w_entry.pack(side="left")
        ttk.Label(cframe, text=" × ").pack(side="left")
        self.h_entry = ttk.Entry(cframe, textvariable=self.h_var, width=8)
        self.h_entry.pack(side="left")

        # --- стартовый код ---
        ttk.Label(left, text="Начальный код:").grid(row=3, column=0, sticky="w", pady=5)
        self.num_var = tk.StringVar(value=str(cfg.get("last_number", "155678")))
        ttk.Entry(left, textvariable=self.num_var, width=36).grid(row=3, column=1, pady=5, sticky="we")

        ttk.Label(left, text="Количество:").grid(row=4, column=0, sticky="w", pady=5)
        self.qty_var = tk.StringVar(value="10")
        ttk.Entry(left, textvariable=self.qty_var, width=36).grid(row=4, column=1, pady=5, sticky="we")

        # --- текст сверху ---
        ttk.Label(left, text="Текст сверху (необязат.):").grid(row=5, column=0, sticky="w", pady=5)
        self.text_var = tk.StringVar(value=cfg.get("top_text", ""))
        ttk.Entry(left, textvariable=self.text_var, width=36).grid(row=5, column=1, pady=5, sticky="we")

        self.rotate_var = tk.BooleanVar(value=bool(cfg.get("rotate180", False)))
        ttk.Checkbutton(left, text="Перевернуть на 180°",
                        variable=self.rotate_var) \
            .grid(row=6, column=0, columnspan=2, sticky="w", pady=5)

        ttk.Button(left, text="Печать", command=self.do_print) \
            .grid(row=7, column=0, columnspan=2, pady=16, ipadx=60)

        left.columnconfigure(1, weight=1)

        # --- предпросмотр ---
        ttk.Label(right, text="Предпросмотр", font=("", 10, "bold")).pack(pady=(0, 8))
        self.preview_label = ttk.Label(right, text="—", anchor="center")
        self.preview_label.pack(fill="both", expand=True)
        self.preview_size_label = ttk.Label(right, text="", foreground="#666")
        self.preview_size_label.pack(pady=(8, 0))

        for v in (self.num_var, self.w_var, self.h_var, self.text_var):
            v.trace_add("write", self.update_preview)
        self.rotate_var.trace_add("write", self.update_preview)

        self._preview_imgtk = None
        self.on_size_change()

    def on_size_change(self, event=None):
        name = self.size_var.get()
        for n, w, h in PRESETS:
            if n == name:
                if w == 0 and h == 0:
                    self.w_entry.config(state="normal")
                    self.h_entry.config(state="normal")
                else:
                    self.w_var.set(str(w))
                    self.h_var.set(str(h))
                    self.w_entry.config(state="disabled")
                    self.h_entry.config(state="disabled")
                break
        self.update_preview()

    def current_size(self):
        try:
            w = float(self.w_var.get().replace(",", "."))
            h = float(self.h_var.get().replace(",", "."))
            if w <= 0 or h <= 0:
                raise ValueError
            return w, h
        except ValueError:
            return None

    def update_preview(self, *args):
        try:
            size = self.current_size()
            if size is None:
                self.preview_label.config(image="", text="Некорректный размер")
                self.preview_size_label.config(text="")
                return
            w_mm, h_mm = size

            start = self.num_var.get().strip() or "0"
            codes = build_sequence(start, 1)
            code = codes[0]

            top_text = self.text_var.get().strip() or None
            img = make_label(code, w_mm, h_mm, top_text)
            if self.rotate_var.get():
                img = img.rotate(180)

            target_w = 380
            if img.width < target_w:
                r = target_w / img.width
                img = img.resize((int(img.width * r), int(img.height * r)), Image.NEAREST)

            bordered = Image.new("RGB", (img.width + 2, img.height + 2), "#888")
            bordered.paste(img, (1, 1))

            self._preview_imgtk = ImageTk.PhotoImage(bordered)
            self.preview_label.config(image=self._preview_imgtk, text="")

            extra = " + 180°" if self.rotate_var.get() else ""
            self.preview_size_label.config(
                text=f"{w_mm:g} × {h_mm:g} мм{extra}   (код: {code})")
        except Exception:
            log("PREVIEW ERROR:\n" + traceback.format_exc())

    def do_print(self):
        printer = self.printer_var.get()
        if not printer:
            messagebox.showerror("Ошибка", "Выбери принтер")
            return

        size = self.current_size()
        if size is None:
            messagebox.showerror("Ошибка", "Некорректный размер этикетки")
            return
        w_mm, h_mm = size

        start = self.num_var.get().strip()
        if not start:
            messagebox.showerror("Ошибка", "Введи начальный код")
            return

        try:
            count = int(self.qty_var.get().strip())
            if count <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Введи корректное количество (>0)")
            return

        rotate   = bool(self.rotate_var.get())
        top_text = self.text_var.get().strip() or None

        codes = build_sequence(start, count)

        try:
            print_labels(printer, codes, w_mm, h_mm, rotate, top_text)
        except Exception as e:
            log("PRINT ERROR:\n" + traceback.format_exc())
            messagebox.showerror("Ошибка печати", f"{e}\n\nПодробности в debug.log")
            return

        # сохраняем следующий код как стартовый для следующего запуска
        next_codes = build_sequence(start, count + 1)
        save_config({
            "printer":     printer,
            "size_name":   self.size_var.get(),
            "custom_w":    w_mm,
            "custom_h":    h_mm,
            "last_number": next_codes[-1],
            "rotate180":   rotate,
            "top_text":    top_text or "",
        })

        msg = f"Отправлено {count} этикеток\n→ {printer}\n{w_mm:g} × {h_mm:g} мм"
        if rotate:
            msg += "\n(перевёрнуто на 180°)"
        if count <= 5:
            msg += "\n\n" + "\n".join(codes)
        else:
            msg += f"\n\n{codes[0]} … {codes[-1]}"
        messagebox.showinfo("Готово", msg)


if __name__ == "__main__":
    try:
        log("--- start ---")
        App().mainloop()
    except Exception:
        err = traceback.format_exc()
        log("CRASH:\n" + err)
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("Ошибка", f"{err}\n\nПодробности в debug.log")
            root.destroy()
        except Exception:
            print(err, file=sys.stderr)