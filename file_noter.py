# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk # ttk widget'larını kullanacağız
from tkinter import messagebox, scrolledtext, Listbox, Scrollbar, Frame, Label # Frame ve Label'ı ttk ile değiştireceğiz
import tkinter.font as tkFont # Fontları ayarlamak için
import sys
import os
import sqlite3
import socket
import threading
import time
import json # Argümanları güvenli göndermek için JSON kullanalım
import subprocess # Dosya konumunu açmak için

try:
    # Windows'a özgü özellikler için
    import ctypes
    HAS_CTYPES = True
except ImportError:
    HAS_CTYPES = False

# --- Ayarlar ---
PORT = 61073 # Uygulamanın iletişim kuracağı özel port (Başka uygulamanın kullanmadığından emin olun)
HOST = '127.0.0.1' # Sadece yerel makinede çalışacak
SOCKET_TIMEOUT = 0.5 # Sunucuya bağlanma denemesi için zaman aşımı (saniye)

try:
    # Veritabanını AppData'da sakla (önerilen)
    APP_DATA_PATH = os.path.join(os.getenv('APPDATA'), 'FileNoter')
    DB_PATH = os.path.join(APP_DATA_PATH, 'filenotes.db')
    os.makedirs(APP_DATA_PATH, exist_ok=True) # Klasörü oluştur (varsa dokunma)
except Exception as e:
    # AppData kullanılamazsa programın yanına kaydet
    print(f"Uyarı: AppData klasörü kullanılamıyor ({e}). Veritabanı program dizinine kaydedilecek.")
    APP_DATA_PATH = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(APP_DATA_PATH, 'filenotes.db')

# --- Global Değişkenler ---
app_root = None # Arka planda çalışacak ana Tkinter örneği
server_socket = None # Sunucu soketi
listener_thread = None # Sunucuyu dinleyen thread
shutdown_event = threading.Event() # Sunucu thread'ini durdurmak için olay
all_notes_window = None # Aktif "Tüm Notlar" penceresini takip et (sadece bir tane)

# --- Stil ve Font Ayarları ---
DEFAULT_FONT = None
LABEL_FONT = None
TEXT_FONT = None
BG_COLOR = None # Tema arka plan rengini saklamak için
FG_COLOR = None # Tema ön plan rengini saklamak için

def setup_styles(root):
    """Uygulama için ttk stillerini ve fontları ayarlar."""
    global DEFAULT_FONT, LABEL_FONT, TEXT_FONT, BG_COLOR, FG_COLOR

    style = ttk.Style(root)
    # Mevcut işletim sistemine uygun bir tema seçmeye çalış
    available_themes = style.theme_names()
    # print("Available themes:", available_themes) # Hangi temaların olduğunu görmek için
    if 'vista' in available_themes:
        style.theme_use('vista')
    elif 'clam' in available_themes:
        style.theme_use('clam')
    # Diğer temaları deneyebilirsiniz: 'alt', 'default', 'classic', 'winnative', 'xpnative'

    # Fontları tanımla
    DEFAULT_FONT = tkFont.nametofont("TkDefaultFont")
    LABEL_FONT = tkFont.Font(family=DEFAULT_FONT.actual("family"), size=DEFAULT_FONT.actual("size"))
    TEXT_FONT = tkFont.Font(family=DEFAULT_FONT.actual("family"), size=DEFAULT_FONT.actual("size"))

    # Temanın arka plan ve ön plan renklerini al (ScrolledText ve Listbox için)
    try:
        BG_COLOR = style.lookup('TFrame', 'background')
        FG_COLOR = style.lookup('TLabel', 'foreground') # Genellikle metin rengi
    except tk.TclError:
        # Tema renklerini alamazsak varsayılan kullan
        BG_COLOR = 'SystemWindow'
        FG_COLOR = 'SystemWindowText'

    # Butonlara biraz iç boşluk ekle
    style.configure('TButton', padding=(10, 5))

# --- Veritabanı İşlemleri ---
# (Veritabanı fonksiyonları aynı kalıyor)

def init_db():
    """Veritabanını ve 'notes' tablosunu oluşturur (eğer yoksa)."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=1.0)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                file_path TEXT PRIMARY KEY,
                note_text TEXT
            )
        ''')
        conn.commit()
    except sqlite3.Error as e:
        _show_startup_error(f"Kritik Veritabanı hatası: {e}\nVeritabanı yolu: {DB_PATH}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

def save_note(file_path, note_text):
    """
    Belirtilen dosya yolu için notu kaydeder veya günceller.
    Eğer note_text boş ("") ise, ilgili kaydı siler.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=1.0)
        cursor = conn.cursor()
        if not note_text:
            print(f"Not metni boş. '{file_path}' için kayıt siliniyor.")
            cursor.execute("DELETE FROM notes WHERE file_path = ?", (file_path,))
        else:
            print(f"Not kaydediliyor/güncelleniyor: '{file_path}'")
            cursor.execute("INSERT OR REPLACE INTO notes (file_path, note_text) VALUES (?, ?)",
                           (file_path, note_text))
        conn.commit()

        if app_root and all_notes_window and all_notes_window.winfo_exists():
            app_root.after(0, all_notes_window.refresh_list)
        return True
    except sqlite3.Error as e:
        show_error(f"Not kaydedilirken/silinirken hata oluştu: {e}", parent=app_root)
        return False
    finally:
        if conn:
            conn.close()

def get_note(file_path):
    """Belirtilen dosya yolu için notu veritabanından getirir."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=1.0)
        cursor = conn.cursor()
        cursor.execute("SELECT note_text FROM notes WHERE file_path = ?", (file_path,))
        result = cursor.fetchone()
        return result[0] if result else ""
    except sqlite3.Error as e:
        show_error(f"Not okunurken hata oluştu: {e}", parent=app_root)
        return ""
    finally:
        if conn:
            conn.close()

def get_all_notes():
    """Veritabanındaki tüm notları {dosya_yolu: not_metni} sözlüğü olarak getirir."""
    notes_data = {}
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=1.0)
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, note_text FROM notes ORDER BY file_path COLLATE NOCASE")
        results = cursor.fetchall()
        notes_data = dict(results)
        return notes_data
    except sqlite3.Error as e:
        show_error(f"Tüm notlar okunurken hata oluştu: {e}", parent=app_root)
        return {}
    finally:
        if conn:
            conn.close()

def delete_note(file_path):
    """Belirtilen dosya yolu için notu veritabanından siler."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=1.0)
        cursor = conn.cursor()
        print(f"Veritabanından siliniyor: '{file_path}'")
        cursor.execute("DELETE FROM notes WHERE file_path = ?", (file_path,))
        conn.commit()

        if app_root and all_notes_window and all_notes_window.winfo_exists():
            app_root.after(0, all_notes_window.refresh_list)
        return True
    except sqlite3.Error as e:
        show_error(f"Not silinirken hata oluştu: {e}", parent=app_root)
        return False
    finally:
        if conn:
            conn.close()


# --- GUI Yardımcı Fonksiyonları ---

def _center_window(win):
    """Verilen pencereyi ekranda ortalar."""
    win.update_idletasks()
    width = win.winfo_width()
    height = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2)
    win.geometry(f'{width}x{height}+{x}+{y}')

def _set_dark_title_bar(window_handle):
    """Windows'ta başlık çubuğunu koyu yapmayı dener."""
    if sys.platform == 'win32' and HAS_CTYPES:
        try:
            HWND = window_handle
            if HWND:
                attribute = 20 # DWMWA_USE_IMMERSIVE_DARK_MODE
                value = 1 # 1 for dark, 0 for light
                ctypes.windll.dwmapi.DwmSetWindowAttribute(HWND, attribute, ctypes.byref(ctypes.c_int(value)), ctypes.sizeof(ctypes.c_int))
        except Exception as e:
            # pass # Başarısız olursa önemli değil
            # print(f"DEBUG: Dark title bar failed: {e}")
            pass


# --- GUI Ana Fonksiyonları (Sunucu tarafından çağrılır) ---

def show_add_note_dialog_internal(parent_root, file_path):
    """Not ekleme/düzenleme Toplevel penceresini gösterir (ttk ve stil ile)."""
    current_note = get_note(file_path)
    file_name_short = os.path.basename(file_path)
    if len(file_name_short) > 40: # Başlıkta çok uzun dosya adlarını kısalt
        file_name_short = file_name_short[:18] + "..." + file_name_short[-18:]

    dialog = tk.Toplevel(parent_root)
    dialog.title(f"'{file_name_short}' için Not")
    dialog.geometry("500x400") # Biraz daha geniş ve yüksek
    dialog.minsize(400, 300)
    dialog.configure(bg=BG_COLOR) # Toplevel arka planını tema ile uyumlu yap
    dialog.attributes("-topmost", True)

    try:
        hwnd = int(dialog.frame(), 16)
        _set_dark_title_bar(hwnd)
    except: pass

    # Ana Çerçeve (Padding eklemek için)
    main_frame = ttk.Frame(dialog, padding=(15, 15, 15, 10)) # Kenarlara daha fazla boşluk
    main_frame.pack(expand=True, fill="both")

    # Widget'ları oluştur ve yerleştir
    label_text = f"'{os.path.basename(file_path)}' dosyası için notunuz:"
    label = ttk.Label(main_frame, text=label_text, font=LABEL_FONT, wraplength=450) # Uzun dosya adları için satır kaydırma
    label.pack(pady=(0, 10), anchor='w') # Altına boşluk

    # ScrolledText için çerçeve (kenarlık veya farklı arka plan gerekirse)
    text_container_frame = ttk.Frame(main_frame, relief="solid", borderwidth=1) # İnce bir kenarlık
    text_container_frame.pack(expand=True, fill="both", pady=(0, 15)) # Altına boşluk

    text_area = scrolledtext.ScrolledText(
        text_container_frame,
        wrap=tk.WORD,
        height=10,
        width=50,
        font=TEXT_FONT,
        bg=BG_COLOR, # Tema arka planı
        fg=FG_COLOR, # Tema metin rengi
        padx=5, # Metin alanı içine boşluk
        pady=5,
        relief=tk.FLAT, # Kendi kenarlığını kaldır
        borderwidth=0
    )
    text_area.pack(expand=True, fill="both")
    text_area.insert(tk.INSERT, current_note)
    text_area.focus_set()

    # Butonlar için çerçeve
    button_frame = ttk.Frame(main_frame)
    # button_frame.pack(pady=(10, 0), fill=tk.X, anchor='e') # Sağa yaslı
    button_frame.pack(fill=tk.X, anchor='se') # Sağa ve alta yaslı

    # Ayırıcı (opsiyonel)
    # sep = ttk.Separator(button_frame, orient='horizontal')
    # sep.pack(fill='x', pady=(0, 10))

    # Kapatma ve kaydetme fonksiyonları
    def on_save():
        new_note = text_area.get("1.0", tk.END).strip()
        save_note(file_path, new_note)
        dialog.destroy()

    def on_close():
        dialog.destroy()

    # Butonlar (ttk.Button kullanarak ve sağa yaslayarak)
    cancel_button = ttk.Button(button_frame, text="İptal", command=on_close, width=10)
    cancel_button.pack(side=tk.RIGHT, padx=(5, 0)) # Sağında boşluk yok
    save_button = ttk.Button(button_frame, text="Kaydet", command=on_save, width=10, style="Accent.TButton") # Varsa vurgulu stil dene
    save_button.pack(side=tk.RIGHT, padx=(0, 5)) # Sağına boşluk

    # Olaylar ve kısayollar
    dialog.protocol("WM_DELETE_WINDOW", on_close)
    dialog.bind('<Control-Return>', lambda e: on_save())
    dialog.bind('<Control-s>', lambda e: on_save()) # Ctrl+S ile kaydet
    dialog.bind('<Escape>', lambda e: on_close())

    _center_window(dialog)
    dialog.lift()
    dialog.after(100, lambda: dialog.attributes("-topmost", False))

def show_view_note_dialog_internal(parent_root, file_path):
    """Notu görüntüleme Toplevel penceresini gösterir (ttk ve stil ile)."""
    note_text = get_note(file_path)
    file_name = os.path.basename(file_path)
    file_name_short = file_name
    if len(file_name_short) > 40:
        file_name_short = file_name_short[:18] + "..." + file_name_short[-18:]

    if not note_text:
        messagebox.showinfo(f"'{file_name_short}' için Not", f"Bu dosya için kayıtlı bir not bulunamadı.", parent=parent_root)
        return

    dialog = tk.Toplevel(parent_root)
    dialog.title(f"'{file_name_short}' Notu")
    dialog.geometry("500x400")
    dialog.minsize(400, 300)
    dialog.configure(bg=BG_COLOR)
    dialog.attributes("-topmost", True)

    try:
        hwnd = int(dialog.frame(), 16)
        _set_dark_title_bar(hwnd)
    except: pass

    main_frame = ttk.Frame(dialog, padding=(15, 15, 15, 10))
    main_frame.pack(expand=True, fill="both")

    # Sadece okunabilir metin alanı
    text_container_frame = ttk.Frame(main_frame, relief="solid", borderwidth=1)
    text_container_frame.pack(expand=True, fill="both", pady=(0, 15))

    text_area = scrolledtext.ScrolledText(
        text_container_frame,
        wrap=tk.WORD,
        height=10,
        width=50,
        font=TEXT_FONT,
        bg=BG_COLOR,
        fg=FG_COLOR,
        padx=5,
        pady=5,
        relief=tk.FLAT,
        borderwidth=0
    )
    text_area.pack(expand=True, fill="both")
    text_area.insert(tk.INSERT, note_text)
    text_area.config(state=tk.DISABLED) # Düzenlemeyi engelle

    def on_close():
        dialog.destroy()

    # Kapat butonu için çerçeve
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(fill=tk.X, anchor='se')

    close_button = ttk.Button(button_frame, text="Kapat", command=on_close, width=10)
    close_button.pack(side=tk.RIGHT)

    dialog.protocol("WM_DELETE_WINDOW", on_close)
    dialog.bind('<Escape>', lambda e: on_close())

    _center_window(dialog)
    dialog.lift()
    dialog.after(100, lambda: dialog.attributes("-topmost", False))


class AllNotesWindow(tk.Toplevel):
    """Tüm notları listeleyen ve yöneten pencere sınıfı (ttk ve stil ile)."""
    def __init__(self, parent):
        global all_notes_window, style # Stili globalden veya parent'tan almamız gerekebilir
        if all_notes_window and all_notes_window.winfo_exists():
            print("Mevcut 'Tüm Notlar' penceresine odaklanılıyor.")
            all_notes_window.lift()
            all_notes_window.focus_set()
            self.after(0, self.destroy)
            return

        super().__init__(parent)
        all_notes_window = self
        self.parent = parent
        self.notes_data = {}

        # Stili al (setup_styles çağrılmış olmalı)
        try:
            self.style = ttk.Style(self)
            # Temanın renklerini tekrar alalım, Toplevel için farklı olabilir
            self.bg_color = self.style.lookup('TFrame', 'background')
            self.fg_color = self.style.lookup('TLabel', 'foreground')
            self.select_bg = self.style.lookup('TListbox', 'selectbackground', default='#0078D7')
            self.select_fg = self.style.lookup('TListbox', 'selectforeground', default='white')
            self.focus_color = self.style.lookup('TButton', 'focuscolor', default='blue')
        except Exception: # Eğer stil alınamazsa varsayılan renkler kullanılır
             self.bg_color = BG_COLOR or 'SystemWindow'
             self.fg_color = FG_COLOR or 'SystemWindowText'
             self.select_bg = '#0078D7'
             self.select_fg = 'white'
             self.focus_color = 'blue'


        self.title("Tüm FileNoter Notları")
        self.geometry("750x550") # Biraz daha büyük
        self.minsize(550, 350)
        self.configure(bg=self.bg_color) # Arka plan rengini ayarla
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.attributes("-topmost", True)

        try:
            hwnd = int(self.frame(), 16)
            _set_dark_title_bar(hwnd)
        except: pass

        # --- Ana Çerçeve ve İç Düzen ---
        main_frame = ttk.Frame(self, padding=(10, 10, 10, 5))
        main_frame.pack(expand=True, fill="both")

        main_frame.columnconfigure(0, weight=3) # Sol sütun (liste)
        main_frame.columnconfigure(1, weight=0) # Ayırıcı
        main_frame.columnconfigure(2, weight=4) # Sağ sütun (metin alanı)
        main_frame.rowconfigure(1, weight=1)    # Widget'ların olduğu satır dikeyde genişlesin

        # --- Etiketler ---
        ttk.Label(main_frame, text="Not Alınan Dosyalar:", font=LABEL_FONT).grid(row=0, column=0, sticky='nw', pady=(0, 5))
        ttk.Label(main_frame, text="Seçili Dosyanın Notu:", font=LABEL_FONT).grid(row=0, column=2, sticky='nw', pady=(0, 5))

        # --- Sol Taraf: Dosya Listesi ---
        list_frame = ttk.Frame(main_frame)
        list_frame.grid(row=1, column=0, sticky='nsew', padx=(0, 5)) # Sağa boşluk
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.listbox_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.listbox = Listbox(
            list_frame,
            yscrollcommand=self.listbox_scrollbar.set,
            exportselection=False,
            font=TEXT_FONT,
            bg=self.bg_color, # Tema arka planı
            fg=self.fg_color, # Tema metin rengi
            highlightthickness=1,
            highlightbackground=self.bg_color, # Kenarlık rengi
            highlightcolor=self.focus_color, # Odak rengi
            selectbackground=self.select_bg, # Seçim arka planı
            selectforeground=self.select_fg, # Seçim metin rengi
            relief=tk.FLAT,
            borderwidth=0
        )
        self.listbox_scrollbar.config(command=self.listbox.yview)

        # Listbox ve scrollbar'ı grid ile yerleştir
        self.listbox.grid(row=0, column=0, sticky='nsew')
        self.listbox_scrollbar.grid(row=0, column=1, sticky='ns')

        # --- Dikey Ayırıcı ---
        sep = ttk.Separator(main_frame, orient='vertical')
        sep.grid(row=1, column=1, sticky='ns', padx=5)

        # --- Sağ Taraf: Not Görüntüleyici ---
        # Note_frame'i oluştur ve grid ile yerleştir
        note_frame = ttk.Frame(main_frame)
        note_frame.grid(row=1, column=2, sticky='nsew', padx=(5, 0)) # Sola boşluk
        # note_frame'in içindeki satır ve sütunların genişlemesini sağla
        note_frame.rowconfigure(0, weight=1)
        note_frame.columnconfigure(0, weight=1)

        # ScrolledText için container (kenarlık vs. için)
        # Bu container'ı note_frame içinde grid ile yerleştir
        text_container_frame = ttk.Frame(note_frame, relief="solid", borderwidth=1)
        text_container_frame.grid(row=0, column=0, sticky='nsew') # note_frame içinde tek eleman

        # text_container_frame'in de içindekilerin genişlemesi için konfigüre et
        text_container_frame.rowconfigure(0, weight=1)
        text_container_frame.columnconfigure(0, weight=1)

        # ScrolledText widget'ını oluştur
        self.note_text_area = scrolledtext.ScrolledText(
            text_container_frame, # Parent olarak container'ı ver
            wrap=tk.WORD,
            height=10, # Başlangıç yüksekliği
            width=40,  # Başlangıç genişliği
            font=TEXT_FONT,
            bg=self.bg_color,
            fg=self.fg_color,
            padx=5,
            pady=5,
            relief=tk.FLAT,
            borderwidth=0,
            state=tk.DISABLED # Başlangıçta sadece okunabilir
        )
        # ScrolledText'i text_container_frame içinde grid ile yerleştir
        self.note_text_area.grid(row=0, column=0, sticky='nsew') # container içinde tek eleman

        # --- Alt Butonlar ---
        button_frame = ttk.Frame(self, padding=(10, 5, 10, 10))
        button_frame.pack(fill=tk.X)

        refresh_button = ttk.Button(button_frame, text="Yenile", command=self.refresh_list, width=10)
        refresh_button.pack(side=tk.LEFT, padx=(0,5))
        remove_button = ttk.Button(button_frame, text="Kaldır", command=self.remove_selected_note, width=10)
        remove_button.pack(side=tk.LEFT, padx=(0, 5))
        edit_button = ttk.Button(button_frame, text="Düzenle", command=self.edit_selected_note, width=10)
        edit_button.pack(side=tk.LEFT)
        close_button = ttk.Button(button_frame, text="Kapat", command=self.on_close, width=10)
        close_button.pack(side=tk.RIGHT)

        # --- Olay Bağlantıları ---
        self.listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.listbox.bind("<Double-Button-1>", self.edit_selected_note)
        self.listbox.bind("<Button-3>", self.on_right_click)
        self.listbox.bind("<Delete>", self.remove_selected_note)

        # --- Başlangıç ---
        self.refresh_list()
        _center_window(self)
        self.lift()
        self.after(100, lambda: self.attributes("-topmost", False))

    # refresh_list, on_listbox_select, edit_selected_note, on_right_click, remove_selected_note, on_close
    # metodları aynı kalabilir. Değişiklik sadece __init__ içindeki layout kısmındaydı.

    def refresh_list(self):
        """Listbox'ı günceller."""
        print("Liste yenileniyor...")
        self.notes_data = get_all_notes()
        current_selection = self.listbox.curselection()
        selected_path = self.listbox.get(current_selection[0]) if current_selection else None

        # Seçimi sakla, listeyi temizlemeden önce indexi al
        original_index = current_selection[0] if current_selection else -1

        self.listbox.config(state=tk.NORMAL)
        self.listbox.delete(0, tk.END)

        # Not alanı temizle
        self.note_text_area.config(state=tk.NORMAL)
        self.note_text_area.delete("1.0", tk.END)
        self.note_text_area.config(state=tk.DISABLED)

        new_index_to_select = -1

        if not self.notes_data:
            self.listbox.insert(tk.END, "(Kayıtlı not bulunamadı)")
            self.listbox.config(state=tk.DISABLED)
        else:
            idx = 0
            # Dosya yollarını sıralı ekle
            sorted_paths = sorted(self.notes_data.keys(), key=str.lower)
            for file_path in sorted_paths:
                display_name = file_path # Tam yolu gösteriyoruz şimdilik
                self.listbox.insert(tk.END, display_name)
                # Yenileme öncesi seçili olanı bulmaya çalış
                if file_path == selected_path:
                    new_index_to_select = idx
                idx += 1

            # Eğer önceki seçili öğe silinmişse veya bulunmuyorsa
            if new_index_to_select == -1 and original_index != -1:
                # Önceki index geçerliyse onu seçmeyi dene
                if original_index < self.listbox.size():
                    new_index_to_select = original_index
                # Değilse ve liste boş değilse son öğeyi seç
                elif self.listbox.size() > 0:
                    new_index_to_select = self.listbox.size() - 1

            # Eğer bir index seçilecekse
            if new_index_to_select != -1:
                 self.listbox.selection_set(new_index_to_select)
                 self.listbox.activate(new_index_to_select) # Aktif öğe yap
                 self.listbox.see(new_index_to_select)      # Görünür alana kaydır
                 self.on_listbox_select(None) # Seçili öğenin notunu yükle

        print(f"{len(self.notes_data)} not yüklendi.")


    def on_listbox_select(self, event=None):
        """Listbox'ta seçim değiştiğinde notu sağdaki alanda gösterir."""
        selection = self.listbox.curselection()
        if not selection: return # Seçim yoksa veya liste devre dışıysa
        selected_path = self.listbox.get(selection[0])

        # Notu sözlükten bul ve göster
        if selected_path in self.notes_data:
            note_content = self.notes_data[selected_path]
            self.note_text_area.config(state=tk.NORMAL)
            self.note_text_area.delete("1.0", tk.END)
            self.note_text_area.insert("1.0", note_content)
            self.note_text_area.config(state=tk.DISABLED)
        elif selected_path == "(Kayıtlı not bulunamadı)":
            self.note_text_area.config(state=tk.NORMAL)
            self.note_text_area.delete("1.0", tk.END)
            self.note_text_area.config(state=tk.DISABLED)
        # else: # Veri ve liste tutarsızsa (olmamalı)
        #     self.note_text_area.config(state=tk.NORMAL)
        #     self.note_text_area.delete("1.0", tk.END)
        #     self.note_text_area.insert("1.0", "Hata: Not bulunamadı!")
        #     self.note_text_area.config(state=tk.DISABLED)


    def edit_selected_note(self, event=None):
        """Listeden seçili notu düzenlemek için dialog açar."""
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("Bilgi", "Lütfen düzenlemek için listeden bir not seçin.", parent=self)
            return
        selected_path = self.listbox.get(selection[0])
        if selected_path == "(Kayıtlı not bulunamadı)": return

        # Doğrudan dialog fonksiyonunu çağır
        show_add_note_dialog_internal(self.parent, selected_path)


    def on_right_click(self, event):
        """Listbox'ta sağ tıklanan öğenin dosya konumunu açar."""
        # Sağ tıklanan noktaya en yakın öğeyi bul ve seç
        nearest = self.listbox.nearest(event.y)
        if nearest != -1:
            # Mevcut seçimi temizleyip yenisini ayarla
            # Bu, sağ tıklandığında her zaman o öğenin seçili olmasını sağlar
            selection = self.listbox.curselection()
            if not selection or selection[0] != nearest:
                 self.listbox.selection_clear(0, tk.END)
                 self.listbox.selection_set(nearest)
                 self.listbox.activate(nearest)
                 # Seçim değiştiyse notu da güncelle (isteğe bağlı)
                 # self.on_listbox_select(None)
        else:
            # Boş bir alana sağ tıklandıysa çık
            return

        # Seçimi tekrar al (nearest ayarlandıktan sonra)
        selection = self.listbox.curselection()
        if not selection: return # Eğer hala seçim yoksa (liste boşken olabilir)

        selected_path = self.listbox.get(selection[0])
        if selected_path == "(Kayıtlı not bulunamadı)": return

        # Dosya var mı kontrol et ve aç
        if not os.path.exists(selected_path):
            dir_path = os.path.dirname(selected_path)
            if os.path.isdir(dir_path):
                if messagebox.askyesno("Dosya Bulunamadı",
                                      f"Dosya bulunamadı:\n{selected_path}\n\nİçeren klasör açılsın mı?\n{dir_path}",
                                      parent=self):
                    try:
                        os.startfile(dir_path)
                    except Exception as e:
                         messagebox.showerror("Hata", f"Klasör açılırken hata oluştu:\n{e}", parent=self)
            else:
                 messagebox.showerror("Hata", f"Dosya veya içeren klasör bulunamadı:\n{selected_path}", parent=self)
            return

        try:
            subprocess.run(['explorer', '/select,', selected_path], check=False)
        except FileNotFoundError:
            messagebox.showerror("Hata", "Windows Gezgini (explorer.exe) bulunamadı.", parent=self)
        except Exception as e:
             messagebox.showerror("Hata", f"Dosya konumu açılırken beklenmedik bir hata oluştu:\n{e}", parent=self)


    def remove_selected_note(self, event=None):
        """Listeden seçili notu kaldırır."""
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("Bilgi", "Lütfen kaldırmak için listeden bir not seçin.", parent=self)
            return

        selected_path = self.listbox.get(selection[0])
        if selected_path == "(Kayıtlı not bulunamadı)": return

        file_name = os.path.basename(selected_path)

        if messagebox.askyesno("Onay",
                               f"'{file_name}' dosyası için alınan not kalıcı olarak silinecektir.\n\nEmin misiniz?",
                               icon='warning', parent=self):
            if delete_note(selected_path):
                print(f"Not başarıyla silindi: {selected_path}")
                # Silme sonrası liste yenilenecek ve seçim ayarlanacak (refresh_list içinde)
            else:
                print(f"Not silinemedi: {selected_path}")


    def on_close(self):
        """Pencere kapatıldığında."""
        global all_notes_window
        print("'Tüm Notlar' penceresi kapatılıyor.")
        all_notes_window = None
        self.destroy()


# --- Hata Gösterme Fonksiyonları ---
# (Aynı kalabilir, Toplevel ve messagebox kullanıyorlar)

def show_error(message, parent=None):
    """Çalışan uygulama sırasında genel bir hata mesajı gösterir."""
    # Arka planda görünmez bir Toplevel oluşturarak messagebox'ı en üste taşı
    err_win = tk.Toplevel(parent if parent and parent.winfo_exists() else None)
    err_win.withdraw() # Pencereyi gösterme
    err_win.attributes("-topmost", True) # Mesaj kutusunun en üstte olmasını sağla
    messagebox.showerror("FileNoter Hatası", message, parent=err_win)
    err_win.after(100, err_win.destroy) # Kısa bir süre sonra gizli pencereyi yok et

def _show_startup_error(message):
    """GUI öncesi veya sunucu hatası gibi durumlarda hata mesajı gösterir."""
    temp_root = tk.Tk()
    temp_root.withdraw()
    temp_root.attributes("-topmost", True)
    messagebox.showerror("FileNoter Hatası", message, parent=temp_root)
    temp_root.destroy()


# --- Sunucu İşlemleri (IPC) ---
# (handle_request ve server_listener aynı kalabilir)

def handle_request(data_str):
    """İstemciden gelen isteği (JSON string) işler ve ilgili GUI eylemini tetikler."""
    global app_root
    if not app_root: return

    try:
        data = json.loads(data_str)
        action = data.get('action')
        file_path = data.get('file_path')

        if not action:
            print("Eylem belirtilmemiş veri alındı:", data_str)
            return

        # GUI işlemlerini app_root'un ana thread'ine güvenli bir şekilde gönder
        if action == "--add" and file_path:
            app_root.after(0, show_add_note_dialog_internal, app_root, file_path)
        elif action == "--view" and file_path:
            app_root.after(0, show_view_note_dialog_internal, app_root, file_path)
        elif action == "--view-all":
            app_root.after(0, lambda: AllNotesWindow(app_root))
        else:
            print(f"Bilinmeyen veya eksik argümanlı eylem alındı: {action}, Path: {file_path}")

    except json.JSONDecodeError:
        print("JSON decode hatası:", data_str)
    except Exception as e:
        print(f"İstek işlenirken hata: {e}")
        # Hata mesajını da ana thread'e gönder
        app_root.after(0, show_error, f"İstek işlenirken hata: {e}", parent=app_root)

def server_listener():
    """Sunucu soketini dinler, gelen bağlantıları kabul eder ve handle_request'e yönlendirir."""
    global server_socket, shutdown_event
    try:
        server_socket.listen(5)
        print(f"Sunucu dinlemede: {HOST}:{PORT}")
    except Exception as e:
        print(f"Sunucu dinlemeye başlama hatası: {e}")
        if app_root:
            app_root.after(0, stop_server) # Hata olursa sunucuyu durdurmayı dene
        return # Thread'den çık

    # select kullanarak soketi non-blocking dinle ve shutdown_event'i kontrol et
    server_socket.settimeout(1.0) # 1 saniye sonra accept bloke olmaz, döngü devam eder

    while not shutdown_event.is_set():
        try:
            # Zaman aşımı ile dinle
            client_socket, addr = server_socket.accept()
            print(f"Bağlantı kabul edildi: {addr}")
            try:
                # Veriyi al (buffer boyutunu artırabiliriz, 2048 genellikle yeterli)
                data = client_socket.recv(2048)
                if data:
                    handle_request(data.decode('utf-8'))
                else:
                    # İstemci bağlantıyı kapattı (veri göndermeden)
                    print(f"İstemci {addr} boş veri gönderdi/bağlantıyı kapattı.")
            except socket.error as e:
                print(f"İstemci soket hatası ({addr}): {e}")
            except Exception as e:
                print(f"İstemci işleme hatası ({addr}): {e}")
            finally:
                # İstemci soketini her zaman kapat
                client_socket.close()
                print(f"Bağlantı kapatıldı: {addr}")

        except socket.timeout:
            # Zaman aşımı oldu, sorun değil, shutdown_event'i tekrar kontrol et
            continue
        except OSError as e:
            # Soket kapatıldığında oluşan beklenen hata (örn. stop_server çağrıldığında)
            if shutdown_event.is_set() and (e.errno == 9 or (hasattr(e, 'winerror') and e.winerror == 10038)): # EBADF or WSAENOTSOCK
                 print("Sunucu soketi kapatıldığı için dinleyici durduruluyor (OSError).")
            else:
                 print(f"Sunucu dinleme hatası (OSError): {e}")
            break # Döngüden çık
        except Exception as e:
            # Diğer beklenmedik hatalar
            print(f"Sunucu dinleme hatası: {e}")
            if not shutdown_event.is_set():
                time.sleep(1) # Tekrar denemeden önce kısa bir süre bekle

    print("Sunucu dinleyici thread sonlandırıldı.")
    # Soketin zaten kapalı olması beklenir ama yine de deneyelim
    temp_socket = server_socket
    server_socket = None
    if temp_socket:
        try: temp_socket.close()
        except: pass


def start_server(initial_action=None, initial_file_path=None):
    """Sunucuyu başlatır (ttk stilleri ile)."""
    global app_root, server_socket, listener_thread, shutdown_event

    app_root = tk.Tk()
    app_root.withdraw() # Ana pencereyi gizle
    setup_styles(app_root) # ttk stillerini ve fontları ayarla
    app_root.protocol("WM_DELETE_WINDOW", stop_server) # Gizli pencere kapatılmaya çalışılırsa durdur

    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR portun hemen tekrar kullanılabilmesini sağlar (test için yararlı)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        # server_socket.listen(5) # Dinlemeyi listener thread içinde başlatacağız
    except socket.error as e:
        _show_startup_error(f"Sunucu başlatılamadı (Port {PORT} kullanılıyor olabilir?):\n{e}")
        try: app_root.destroy()
        except: pass
        app_root = None
        sys.exit(1) # Başlatılamazsa çık

    shutdown_event.clear()
    listener_thread = threading.Thread(target=server_listener, daemon=True)
    listener_thread.start()

    # Eğer başlangıçta bir eylem varsa, sunucu hazır olduktan sonra işle
    if initial_action:
        # handle_request doğrudan çağrılabilir çünkü aynı process içindeyiz
        # Ama yine de after ile ana döngüye bırakmak daha güvenli olabilir
        initial_data = json.dumps({'action': initial_action, 'file_path': initial_file_path})
        app_root.after(100, lambda: handle_request(initial_data)) # Küçük bir gecikme

    print("Tkinter ana döngüsü başlatılıyor...")
    try:
        app_root.mainloop()
    except KeyboardInterrupt:
        print("KeyboardInterrupt algılandı, kapatılıyor...")
        # stop_server() burada zaten mainloop bittiği için çağrılmayabilir,
        # bu yüzden mainloop sonrası garantiye alalım.
    finally:
        print("Tkinter ana döngüsü bitti.")
        # Ana döngü bittiyse (normalde quit ile), sunucuyu durdur
        if not shutdown_event.is_set(): # Eğer zaten durdurulmuyorsa
             stop_server()


def stop_server():
    """Sunucuyu, dinleyici thread'i ve Tkinter uygulamasını düzgünce kapatır."""
    global app_root, server_socket, listener_thread, shutdown_event
    if shutdown_event.is_set():
        print("Kapatma işlemi zaten devam ediyor.")
        return # Zaten kapatılıyorsa tekrar başlatma

    print("Kapatma işlemi başlatılıyor...")
    shutdown_event.set() # Önce olayı ayarla ki thread'ler durabilsin

    # Dinleyici thread'i sonlandır
    if listener_thread and listener_thread.is_alive():
        print("Dinleyici thread'in bitmesi bekleniyor...")
        # Soketi kapatmak, accept() veya recv() çağrısında olan thread'in hata alıp çıkmasını sağlar
        temp_socket_for_shutdown = server_socket
        server_socket = None # Global referansı kaldır
        if temp_socket_for_shutdown:
            print("Sunucu soketi kapatılıyor (thread'i uyandırmak için)...")
            try:
                # shutdown RDWR, bekleyen ve gelecek bağlantıları reddeder
                temp_socket_for_shutdown.shutdown(socket.SHUT_RDWR)
            except OSError as e:
                 # Soket zaten bağlı değilse veya kapalıysa bu hata normaldir
                 # print(f"Soket shutdown hatası (normal olabilir): {e}")
                 pass
            except Exception as e:
                print(f"Soket shutdown sırasında beklenmedik hata: {e}")
            finally:
                try:
                     temp_socket_for_shutdown.close()
                     print("Sunucu soketi kapatıldı.")
                except Exception as e: print(f"Soket kapatma hatası: {e}")

        # Thread'in bitmesini bekle (timeout ile)
        listener_thread.join(timeout=2.0) # Biraz daha uzun bekle
        if listener_thread.is_alive():
            print("Uyarı: Dinleyici thread zaman aşımında bitmedi.")
        listener_thread = None
    else:
         # Eğer thread hiç başlamadıysa veya zaten bittiyse, soketi yine de kapat
         temp_socket = server_socket
         server_socket = None
         if temp_socket:
             try: temp_socket.close(); print("Sunucu soketi (thread yokken) kapatıldı.")
             except: pass


    # Tkinter uygulamasını kapat
    if app_root:
        print("Tkinter root penceresi yok ediliyor...")
        try:
            # app_root.quit() # mainloop'u sonlandırır
            app_root.destroy() # Pencereyi ve tüm alt widget'ları yok eder
            print("Tkinter root penceresi yok edildi.")
        except tk.TclError as e:
            # Zaten yok edilmişse hata verebilir
            print(f"Root pencere yok edilirken hata (normal olabilir): {e}")
        except Exception as e:
            print(f"Root pencere yok etme hatası: {e}")
        finally:
            app_root = None # Global referansı temizle

    print("Kapatma işlemi tamamlandı.")
    # Sunucu instance'ı sys.exit() ile tamamen sonlanmalı
    sys.exit(0) # Başarılı çıkış


def send_request_to_server(action, file_path):
    """Çalışan sunucuya istek gönderir."""
    try:
        # Kısa timeout ile bağlanmayı dene
        with socket.create_connection((HOST, PORT), timeout=SOCKET_TIMEOUT) as client_socket:
            data = {'action': action, 'file_path': file_path}
            message = json.dumps(data).encode('utf-8')
            client_socket.sendall(message)
            # Sunucudan bir yanıt beklemiyoruz, sadece gönderiyoruz
            return True # Bağlantı başarılı
    except (socket.timeout, socket.error, ConnectionRefusedError) as e:
        # Sunucu çalışmıyor veya bağlantı kurulamadı
        # print(f"Sunucuya bağlanılamadı: {e}")
        return False
    except Exception as e:
        # Diğer beklenmedik hatalar
        print(f"İstek gönderirken beklenmedik hata: {e}")
        # Bu durumda bir hata mesajı göstermek iyi olabilir
        _show_startup_error(f"Sunucuya bağlanırken hata:\n{e}")
        return False


# --- Ana Çalıştırma Bloğu ---
if __name__ == "__main__":
    # Veritabanını başlat/kontrol et
    init_db()

    # Komut satırı argümanlarını kontrol et
    if len(sys.argv) < 2:
        # Argüman yoksa, belki "--view-all" varsayılan olarak çalıştırılabilir?
        # Şimdilik hata verelim:
        _show_startup_error("Hata: Eksik komut satırı argümanları.\nKullanım: FileNoter.exe <eylem> [dosya_yolu]\nEylemler: --add, --view, --view-all")
        sys.exit(1)

    current_action = sys.argv[1]
    current_file_path = None

    # Argümanları doğrula
    if current_action in ["--add", "--view"]:
        if len(sys.argv) < 3:
            _show_startup_error(f"Hata: '{current_action}' eylemi için dosya yolu gerekli.")
            sys.exit(1)
        current_file_path = sys.argv[2]
        # Dosya yolunun varlığını kontrol etmek isteyebiliriz ama sunucu tarafında yapılırsa daha iyi
    elif current_action == "--view-all":
        pass # Dosya yolu gerekmez
    else:
         _show_startup_error(f"Hata: Geçersiz eylem '{current_action}'. Beklenen: --add, --view, --view-all")
         sys.exit(1)

    # Çalışan bir sunucu var mı diye kontrol et
    print(f"Eylem '{current_action}' {current_file_path or ''} için sunucuya istek gönderiliyor...")
    server_running = send_request_to_server(current_action, current_file_path)

    if server_running:
        # Sunucu isteği aldı, bu instance çıkabilir
        print("İstek sunucuya başarıyla gönderildi. Bu istemci sonlanıyor.")
        sys.exit(0)
    else:
        # Sunucu çalışmıyor, bu instance sunucu olacak
        print("Çalışan sunucu bulunamadı. Bu instance sunucu olarak başlatılacak...")
        # Sunucuyu başlangıç eylemiyle başlat
        start_server(initial_action=current_action, initial_file_path=current_file_path)
        # start_server içindeki mainloop bittiğinde veya stop_server çağrıldığında
        # program buradan devam eder ve sonlanır.
        print("Ana program sonlanıyor (start_server sonrası).")
        sys.exit(0) # Normalde buraya gelinmemeli, start_server çıkışı yönetir