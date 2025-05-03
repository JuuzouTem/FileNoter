# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox, scrolledtext, Listbox, Scrollbar, Frame, Label
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

# --- Veritabanı İşlemleri ---

def init_db():
    """Veritabanını ve 'notes' tablosunu oluşturur (eğer yoksa)."""
    conn = None
    try:
        # timeout: Veritabanı kilitliyse ne kadar bekleneceği (saniye)
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
        # Başlangıçta kritik bir hata oluşursa göster ve çık
        _show_startup_error(f"Kritik Veritabanı hatası: {e}\nVeritabanı yolu: {DB_PATH}")
        sys.exit(1) # Programdan çık
    finally:
        # Bağlantıyı her zaman kapat
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

        # Not metni boş mu diye kontrol et
        if not note_text:
            # Eğer not boşsa, veritabanından bu dosya yoluyla ilgili kaydı sil
            print(f"Not metni boş. '{file_path}' için kayıt siliniyor.")
            cursor.execute("DELETE FROM notes WHERE file_path = ?", (file_path,))
        else:
            # Not metni boş değilse, normal şekilde kaydet veya güncelle
            print(f"Not kaydediliyor/güncelleniyor: '{file_path}'")
            cursor.execute("INSERT OR REPLACE INTO notes (file_path, note_text) VALUES (?, ?)",
                           (file_path, note_text))

        conn.commit() # Değişiklikleri (silme veya ekleme/güncelleme) onayla

        # "Tüm Notlar" penceresi açıksa listeyi yenile
        if app_root and all_notes_window and all_notes_window.winfo_exists():
            # Değişikliğin hemen yansıması için gecikmesiz çağır
            app_root.after(0, all_notes_window.refresh_list)

        return True # İşlem başarılı

    except sqlite3.Error as e:
        # Hata oluşursa göster
        show_error(f"Not kaydedilirken/silinirken hata oluştu: {e}", parent=app_root)
        return False # İşlem başarısız
    finally:
        # Veritabanı bağlantısını her durumda kapat
        if conn:
            conn.close()

def get_note(file_path):
    """Belirtilen dosya yolu için notu veritabanından getirir."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=1.0)
        cursor = conn.cursor()
        cursor.execute("SELECT note_text FROM notes WHERE file_path = ?", (file_path,))
        result = cursor.fetchone() # Tek bir sonuç veya None döner
        # Sonuç varsa not metnini, yoksa boş string döndür
        return result[0] if result else ""
    except sqlite3.Error as e:
        show_error(f"Not okunurken hata oluştu: {e}", parent=app_root)
        return "" # Hata durumunda boş string dön
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
        # Büyük/küçük harf duyarsız alfanümerik sıralama için COLLATE NOCASE
        cursor.execute("SELECT file_path, note_text FROM notes ORDER BY file_path COLLATE NOCASE")
        results = cursor.fetchall() # Tüm satırları liste olarak al
        notes_data = dict(results) # [(path1, note1), ...] listesini {path1: note1, ...} sözlüğüne çevir
        return notes_data
    except sqlite3.Error as e:
        show_error(f"Tüm notlar okunurken hata oluştu: {e}", parent=app_root)
        return {} # Hata durumunda boş sözlük dön
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

        # Silme işlemi sonrası "Tüm Notlar" penceresi açıksa listeyi yenile
        if app_root and all_notes_window and all_notes_window.winfo_exists():
            app_root.after(0, all_notes_window.refresh_list)

        return True # Başarılı
    except sqlite3.Error as e:
        show_error(f"Not silinirken hata oluştu: {e}", parent=app_root)
        return False # Başarısız
    finally:
        if conn:
            conn.close()

# --- GUI Yardımcı Fonksiyonları ---

def _center_window(win):
    """Verilen pencereyi ekranda ortalar."""
    win.update_idletasks() # Pencere boyutlarının hesaplanmasını sağla
    width = win.winfo_width()
    height = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2)
    win.geometry(f'{width}x{height}+{x}+{y}')

def _set_dark_title_bar(window_handle):
    """Windows'ta başlık çubuğunu koyu yapmayı dener (Başarısız olabilir)."""
    if sys.platform == 'win32' and HAS_CTYPES:
        try:
            HWND = window_handle # Toplevel'ın HWND'sini kullan
            if HWND:
                # Windows 11 22H2+ : 20
                attribute = 20
                # Değer 1: Koyu, 0: Açık
                value = 1
                ctypes.windll.dwmapi.DwmSetWindowAttribute(HWND, attribute, ctypes.byref(ctypes.c_int(value)), ctypes.sizeof(ctypes.c_int))
        except Exception as e:
            # print(f"Başlık çubuğu rengi ayarlanamadı: {e}") # Hata ayıklama için
            pass # Başarısız olursa önemli değil

# --- GUI Ana Fonksiyonları (Sunucu tarafından çağrılır) ---

def show_add_note_dialog_internal(parent_root, file_path):
    """Not ekleme/düzenleme Toplevel penceresini gösterir."""
    current_note = get_note(file_path)

    dialog = tk.Toplevel(parent_root)
    dialog.title(f"'{os.path.basename(file_path)}' için Not")
    dialog.geometry("450x350")
    dialog.minsize(350, 250)
    dialog.attributes("-topmost", True) # Geçici olarak en üste al

    try:
        # Pencere oluşturulduktan sonra HWND alınıp renk ayarlanabilir
        hwnd = int(dialog.frame(), 16)
        _set_dark_title_bar(hwnd)
    except: pass # Başarısız olursa devam et

    # Widget'ları oluştur ve yerleştir
    label = tk.Label(dialog, text=f"'{os.path.basename(file_path)}' dosyası için notunuzu girin:")
    label.pack(pady=(10, 5), padx=10, anchor='w')

    text_frame = Frame(dialog)
    text_frame.pack(expand=True, fill="both", padx=10, pady=(0, 5))
    text_area = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, height=10, width=50)
    text_area.pack(expand=True, fill="both")
    text_area.insert(tk.INSERT, current_note) # Mevcut notu yükle
    text_area.focus_set() # Metin alanına odaklan

    # Kaydetme ve kapatma fonksiyonları
    def on_save():
        new_note = text_area.get("1.0", tk.END).strip() # Metni al, baştaki/sondaki boşlukları temizle
        # save_note fonksiyonu artık boş metin durumunda silme işlemini yapacak
        save_note(file_path, new_note)
        dialog.destroy() # Pencereyi kapat

    def on_close():
        dialog.destroy() # Pencereyi kapat

    # Butonlar
    button_frame = Frame(dialog)
    button_frame.pack(pady=(5, 10))
    save_button = tk.Button(button_frame, text="Kaydet", command=on_save, width=10)
    save_button.pack(side=tk.LEFT, padx=5)
    cancel_button = tk.Button(button_frame, text="İptal", command=on_close, width=10)
    cancel_button.pack(side=tk.LEFT, padx=5)

    # Pencere olayları ve kısayollar
    dialog.protocol("WM_DELETE_WINDOW", on_close) # Pencere kapatma (X) butonu
    dialog.bind('<Control-Return>', lambda event=None: on_save()) # Ctrl+Enter ile kaydet
    dialog.bind('<Escape>', lambda event=None: on_close()) # Esc ile kapat

    _center_window(dialog) # Pencereyi ortala
    dialog.lift() # Pencereyi diğerlerinin önüne getir
    # Kısa bir süre sonra topmost özelliğini kaldır ki diğer pencerelerle etkileşim kurulabilsin
    dialog.after(100, lambda: dialog.attributes("-topmost", False))


def show_view_note_dialog_internal(parent_root, file_path):
    """Notu görüntüleme Toplevel penceresini gösterir."""
    note_text = get_note(file_path)
    file_name = os.path.basename(file_path)

    # Eğer not yoksa, bilgi ver ve pencereyi açma
    if not note_text:
        messagebox.showinfo(f"'{file_name}' için Not", f"Bu dosya için kayıtlı bir not bulunamadı.", parent=parent_root)
        return

    # Not varsa pencereyi oluştur
    dialog = tk.Toplevel(parent_root)
    dialog.title(f"'{file_name}' Notu")
    dialog.geometry("450x350")
    dialog.minsize(350, 250)
    dialog.attributes("-topmost", True)

    try:
        hwnd = int(dialog.frame(), 16)
        _set_dark_title_bar(hwnd)
    except: pass

    # Sadece okunabilir metin alanı
    text_frame = Frame(dialog)
    text_frame.pack(expand=True, fill="both", padx=10, pady=10)
    text_area = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, height=10, width=50)
    text_area.pack(expand=True, fill="both")
    text_area.insert(tk.INSERT, note_text) # Notu yükle
    text_area.config(state=tk.DISABLED) # Düzenlemeyi engelle

    def on_close():
        dialog.destroy() # Pencereyi kapat

    # Kapat butonu
    close_button = tk.Button(dialog, text="Kapat", command=on_close, width=10)
    close_button.pack(pady=(0, 10))

    # Olaylar
    dialog.protocol("WM_DELETE_WINDOW", on_close)
    dialog.bind('<Escape>', lambda event=None: on_close())

    _center_window(dialog)
    dialog.lift()
    dialog.after(100, lambda: dialog.attributes("-topmost", False))


class AllNotesWindow(tk.Toplevel):
    """Tüm notları listeleyen ve yöneten pencere sınıfı."""
    def __init__(self, parent):
        global all_notes_window
        # Eğer zaten bir "Tüm Notlar" penceresi açıksa, yenisini açmak yerine ona odaklan
        if all_notes_window and all_notes_window.winfo_exists():
            print("Mevcut 'Tüm Notlar' penceresine odaklanılıyor.")
            all_notes_window.lift() # Pencereyi öne getir
            all_notes_window.focus_set() # Klavye odağını ver
            # Bu yeni (gereksiz) Toplevel instance'ını hemen yok et
            self.after(0, self.destroy)
            return # Yeni pencere oluşturma

        # İlk defa açılıyorsa veya önceki kapanmışsa, normal Toplevel başlatma
        super().__init__(parent)
        all_notes_window = self # Bu instance'ı global değişkene ata
        self.parent = parent
        self.notes_data = {} # Notları {path: note} olarak sakla

        # Pencere ayarları
        self.title("Tüm FileNoter Notları")
        self.geometry("700x500") # Başlangıç boyutu
        self.minsize(500, 300) # Minimum boyut
        self.protocol("WM_DELETE_WINDOW", self.on_close) # Kapatma butonunu yakala
        self.attributes("-topmost", True) # Geçici en üstte

        try:
            hwnd = int(self.frame(), 16)
            _set_dark_title_bar(hwnd)
        except: pass

        # --- Widget'lar ---
        main_frame = Frame(self)
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)

        # Sol Taraf: Dosya Listesi
        left_frame = Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        Label(left_frame, text="Not Alınan Dosyalar:").pack(anchor='w', pady=(0, 2))
        list_frame = Frame(left_frame)
        list_frame.pack(expand=True, fill="both")
        self.listbox_scrollbar = Scrollbar(list_frame, orient=tk.VERTICAL)
        self.listbox = Listbox(list_frame, yscrollcommand=self.listbox_scrollbar.set, exportselection=False)
        self.listbox_scrollbar.config(command=self.listbox.yview)
        self.listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, expand=True, fill="both")

        # Sağ Taraf: Not Görüntüleyici
        right_frame = Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        Label(right_frame, text="Seçili Dosyanın Notu:").pack(anchor='w', pady=(0, 2))
        self.note_text_area = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, height=10, width=40)
        self.note_text_area.pack(expand=True, fill="both")
        self.note_text_area.config(state=tk.DISABLED) # Başlangıçta sadece okunabilir

        # Alt Butonlar
        button_frame = Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        refresh_button = tk.Button(button_frame, text="Yenile", command=self.refresh_list, width=10)
        refresh_button.pack(side=tk.LEFT, padx=(0,5)) # Sağına boşluk ekle
        remove_button = tk.Button(button_frame, text="Kaldır", command=self.remove_selected_note, width=10)
        remove_button.pack(side=tk.LEFT) # Yenile'nin yanına ekle
        close_button = tk.Button(button_frame, text="Kapat", command=self.on_close, width=10)
        close_button.pack(side=tk.RIGHT) # Kapat butonu sağda kalacak

        # --- Olay Bağlantıları ---
        self.listbox.bind("<Double-Button-1>", self.on_double_click) # Sol çift tıklama
        self.listbox.bind("<Button-3>", self.on_right_click) # Sağ tıklama
        self.listbox.bind("<Delete>", self.remove_selected_note) # Delete tuşu

        # --- Başlangıç ---
        self.refresh_list() # Listeyi ilk defa doldur
        _center_window(self) # Ortala
        self.lift() # Öne getir
        self.after(100, lambda: self.attributes("-topmost", False)) # Topmost'u kaldır


    def refresh_list(self):
        """Listbox'ı veritabanındaki güncel notlarla doldurur."""
        print("Liste yenileniyor...")
        self.notes_data = get_all_notes() # Tüm notları al
        current_selection = self.listbox.curselection() # Mevcut seçimi sakla
        selected_path = self.listbox.get(current_selection[0]) if current_selection else None

        self.listbox.config(state=tk.NORMAL) # Listbox'ı aktif et (eğer devre dışıysa)
        self.listbox.delete(0, tk.END) # Mevcut listeyi temizle
        # Not alanını temizle
        self.note_text_area.config(state=tk.NORMAL)
        self.note_text_area.delete("1.0", tk.END)
        self.note_text_area.config(state=tk.DISABLED)

        new_index_to_select = -1 # Yeniden seçilecek index

        if not self.notes_data:
            # Not yoksa bilgi mesajı göster ve listeyi devre dışı bırak
            self.listbox.insert(tk.END, "(Kayıtlı not bulunamadı)")
            self.listbox.config(state=tk.DISABLED)
        else:
            # Not varsa, dosya yollarını listeye ekle
            idx = 0
            sorted_paths = sorted(self.notes_data.keys(), key=str.lower)
            for file_path in sorted_paths:
                self.listbox.insert(tk.END, file_path)
                # Eğer silinmeden önceki seçili öğe buysa, indexini sakla
                if file_path == selected_path:
                    new_index_to_select = idx
                idx += 1
            # Silme sonrası, silinen öğenin yerine bir sonrakini/öncekini seçmeye çalış
            if new_index_to_select == -1 and current_selection:
                # Önceki seçim artık listede yoksa
                original_index = current_selection[0]
                if original_index < self.listbox.size():
                     # Önceki index hala geçerliyse onu seç
                     new_index_to_select = original_index
                elif self.listbox.size() > 0:
                     # Liste boş değilse son öğeyi seç
                     new_index_to_select = self.listbox.size() -1

            # Eğer yeniden seçilecek bir index bulunduysa
            if new_index_to_select != -1:
                 self.listbox.selection_set(new_index_to_select) # Öğeyi seç
                 self.listbox.see(new_index_to_select) # Seçili öğeyi görünür alana kaydır
                 # Seçili öğenin notunu tekrar göster
                 self.on_double_click(None) # Sahte olay göndererek tetikle

        print(f"{len(self.notes_data)} not yüklendi.")


    def on_double_click(self, event=None):
        """Listbox'ta çift tıklanan öğenin notunu sağdaki alanda gösterir."""
        selection = self.listbox.curselection() # Seçili öğenin indeksini al
        if not selection: return # Seçim yoksa bir şey yapma
        selected_path = self.listbox.get(selection[0]) # Seçili dosya yolunu al
        # Notu sözlükten bul ve göster
        if selected_path in self.notes_data:
            note_content = self.notes_data[selected_path]
            self.note_text_area.config(state=tk.NORMAL) # Yazılabilir yap
            self.note_text_area.delete("1.0", tk.END)   # Önceki içeriği sil
            self.note_text_area.insert("1.0", note_content) # Yeni notu ekle
            self.note_text_area.config(state=tk.DISABLED) # Tekrar sadece okunabilir yap
        # else: # Hata durumu refresh_list'te ele alınmalı (öğe zaten listede yoksa buraya gelmez)


    def on_right_click(self, event):
        """Listbox'ta sağ tıklanan öğenin dosya konumunu Windows Gezgini'nde açar."""
        selection = self.listbox.curselection()
        # Eğer sağ tıklanan öğe seçili değilse, onu seçili hale getir
        if not selection:
             nearest = self.listbox.nearest(event.y) # Tıklama noktasına en yakın öğe
             if nearest != -1:
                 self.listbox.selection_clear(0, tk.END) # Diğer seçimleri temizle
                 self.listbox.selection_set(nearest) # Bu öğeyi seç
                 self.listbox.activate(nearest) # Aktif öğe yap
                 selection = self.listbox.curselection() # Seçimi tekrar al
             else:
                 return # Boş alana tıklandıysa çık

        if not selection: return # Hâlâ seçim yoksa

        selected_path = self.listbox.get(selection[0]) # Seçili dosya yolunu al

        # Dosyanın hala var olup olmadığını kontrol et
        if not os.path.exists(selected_path):
            # Dosya yoksa, içeren klasörü açmayı öner
            dir_path = os.path.dirname(selected_path)
            if os.path.isdir(dir_path):
                if messagebox.askyesno("Dosya Bulunamadı",
                                      f"Dosya bulunamadı:\n{selected_path}\n\nİçeren klasör açılsın mı?\n{dir_path}",
                                      parent=self):
                    try:
                        os.startfile(dir_path) # Klasörü varsayılan programla aç
                    except Exception as e:
                         messagebox.showerror("Hata", f"Klasör açılırken hata oluştu:\n{e}", parent=self)
            else:
                 # Ne dosya ne de klasör varsa hata göster
                 messagebox.showerror("Hata", f"Dosya veya içeren klasör bulunamadı:\n{selected_path}", parent=self)
            return # Fonksiyondan çık

        # Dosya varsa, explorer.exe ile seçili olarak açmayı dene
        try:
            # check=True kaldırıldı, explorer.exe'nin 0 dışı çıkış kodu hata vermeyecek
            subprocess.run(['explorer', '/select,', selected_path])
        except FileNotFoundError:
            # explorer.exe bulunamazsa (çok nadir)
            messagebox.showerror("Hata", "Windows Gezgini (explorer.exe) bulunamadı.", parent=self)
        except Exception as e:
             # Diğer beklenmedik hatalar
             messagebox.showerror("Hata", f"Dosya konumu açılırken beklenmedik bir hata oluştu:\n{e}", parent=self)


    def remove_selected_note(self, event=None):
        """Listeden seçili notu kaldırır."""
        selection = self.listbox.curselection() # Seçili öğenin indeksini al
        if not selection:
            messagebox.showinfo("Bilgi", "Lütfen kaldırmak için listeden bir not seçin.", parent=self)
            return

        selected_path = self.listbox.get(selection[0]) # Seçili dosya yolunu al
        file_name = os.path.basename(selected_path) # Sadece dosya adını al (mesaj için)

        # Kullanıcıdan onay iste
        if messagebox.askyesno("Onay",
                               f"'{file_name}' dosyası için alınan not kalıcı olarak silinecektir.\n\nEmin misiniz?",
                               icon='warning', parent=self):
            # Onay verildiyse, veritabanından silme fonksiyonunu çağır
            if delete_note(selected_path):
                # Silme başarılıysa, liste otomatik olarak refresh_list ile güncellenecek
                # (delete_note içindeki app_root.after çağrısı sayesinde)
                print(f"Not başarıyla silindi: {selected_path}")
                # Not alanını hemen temizle (opsiyonel ama iyi görünür)
                self.note_text_area.config(state=tk.NORMAL)
                self.note_text_area.delete("1.0", tk.END)
                self.note_text_area.config(state=tk.DISABLED)
            else:
                # Silme başarısız olduysa, hata mesajı zaten delete_note içinde gösterildi.
                print(f"Not silinemedi: {selected_path}")


    def on_close(self):
        """Pencere kapatıldığında global referansı temizler ve pencereyi yok eder."""
        global all_notes_window
        print("'Tüm Notlar' penceresi kapatılıyor.")
        all_notes_window = None # Başka bir kopyanın açılabilmesi için referansı sıfırla
        self.destroy() # Pencereyi yok et


# --- Hata Gösterme Fonksiyonları ---

def show_error(message, parent=None):
    """Çalışan uygulama sırasında genel bir hata mesajı gösterir."""
    if parent and parent.winfo_exists():
        try:
            err_win = tk.Toplevel(parent)
            err_win.withdraw()
            err_win.attributes("-topmost", True)
            messagebox.showerror("FileNoter Hatası", message, parent=err_win)
            err_win.destroy()
        except tk.TclError:
             _show_startup_error(message)
    else:
        _show_startup_error(message)

def _show_startup_error(message):
    """GUI öncesi veya sunucu hatası gibi durumlarda hata mesajı gösterir."""
    temp_root = tk.Tk()
    temp_root.withdraw()
    temp_root.attributes("-topmost", True)
    messagebox.showerror("FileNoter Hatası", message, parent=temp_root)
    temp_root.destroy()


# --- Sunucu İşlemleri (IPC - İşlemler Arası İletişim) ---

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
            app_root.after(0, stop_server)
        return

    while not shutdown_event.is_set():
        try:
            import select
            readable, _, exceptional = select.select([server_socket], [], [server_socket], 1.0)

            if shutdown_event.is_set(): break

            if server_socket in readable:
                client_socket, addr = server_socket.accept()
                try:
                    data = client_socket.recv(2048)
                    if data:
                        handle_request(data.decode('utf-8'))
                    else: pass
                except socket.error as e: pass
                except Exception as e: print(f"İstemci işleme hatası: {e}")
                finally: client_socket.close()
            elif server_socket in exceptional:
                 print("Sunucu soketinde hata oluştu.")
                 break

        except socket.timeout: continue
        except OSError as e:
             if hasattr(e, 'winerror') and e.winerror == 10038 or e.errno == 9:
                 print("Sunucu soketi kapatıldı (OSError).")
             else:
                 print(f"Sunucu dinleme hatası (OSError): {e}")
             break
        except Exception as e:
            print(f"Sunucu dinleme hatası: {e}")
            time.sleep(1)

    print("Sunucu dinleyici thread sonlandırıldı.")
    temp_socket = server_socket
    server_socket = None
    if temp_socket:
        try: temp_socket.close()
        except: pass


def start_server(initial_action=None, initial_file_path=None):
    """Sunucuyu (arka plan Tkinter uygulamasını ve soket dinleyiciyi) başlatır."""
    global app_root, server_socket, listener_thread, shutdown_event

    app_root = tk.Tk()
    app_root.withdraw()
    app_root.protocol("WM_DELETE_WINDOW", stop_server)

    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
    except socket.error as e:
        _show_startup_error(f"Sunucu başlatılamadı (Port {PORT} kullanılıyor olabilir?):\n{e}")
        try: app_root.destroy()
        except: pass
        app_root = None
        sys.exit(1)

    shutdown_event.clear()
    listener_thread = threading.Thread(target=server_listener, daemon=True)
    listener_thread.start()

    if initial_action:
         initial_data = json.dumps({'action': initial_action, 'file_path': initial_file_path})
         handle_request(initial_data)

    print("Tkinter ana döngüsü başlatılıyor...")
    try:
        app_root.mainloop()
    except KeyboardInterrupt:
        print("KeyboardInterrupt algılandı, kapatılıyor...")
        stop_server()
    print("Tkinter ana döngüsü bitti.")
    stop_server()

def stop_server():
    """Sunucuyu, dinleyici thread'i ve Tkinter uygulamasını düzgünce kapatır."""
    global app_root, server_socket, listener_thread, shutdown_event
    if shutdown_event.is_set(): return
    print("Kapatma işlemi başlatılıyor...")
    shutdown_event.set()

    temp_socket = server_socket
    server_socket = None
    if temp_socket:
        print("Sunucu soketi kapatılıyor...")
        try: temp_socket.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        except Exception as e: print(f"Soket shutdown hatası: {e}")
        finally:
             try:
                 temp_socket.close()
                 print("Sunucu soketi kapatıldı.")
             except Exception as e: print(f"Soket kapatma hatası: {e}")

    if listener_thread and listener_thread.is_alive():
        print("Dinleyici thread'in bitmesi bekleniyor...")
        listener_thread.join(timeout=1.5)
        if listener_thread.is_alive():
            print("Uyarı: Dinleyici thread zaman aşımında bitmedi.")
        listener_thread = None

    if app_root:
        print("Tkinter root penceresi yok ediliyor...")
        try:
            app_root.quit()
            app_root.destroy()
            print("Tkinter root penceresi yok edildi.")
        except Exception as e: print(f"Root pencere yok etme hatası: {e}")
        finally: app_root = None

    print("Kapatma işlemi tamamlandı.")
    sys.exit(0)


def send_request_to_server(action, file_path):
    """Çalışan sunucuya belirtilen eylem ve dosya yolu ile istek gönderir."""
    try:
        with socket.create_connection((HOST, PORT), timeout=SOCKET_TIMEOUT) as client_socket:
            data = {'action': action, 'file_path': file_path}
            message = json.dumps(data).encode('utf-8')
            client_socket.sendall(message)
            return True
    except (socket.timeout, socket.error, ConnectionRefusedError):
        return False
    except Exception as e:
        print(f"İstek gönderirken beklenmedik hata: {e}")
        _show_startup_error(f"Sunucuya bağlanırken hata:\n{e}")
        return False


# --- Ana Çalıştırma Bloğu (Programın başlangıç noktası) ---
if __name__ == "__main__":
    init_db()

    if len(sys.argv) < 2:
        _show_startup_error("Hata: Eksik komut satırı argümanları.\nKullanım: FileNoter.exe <eylem> [dosya_yolu]")
        sys.exit(1)

    current_action = sys.argv[1]
    current_file_path = None

    if current_action in ["--add", "--view"]:
        if len(sys.argv) < 3:
            _show_startup_error(f"Hata: '{current_action}' eylemi için dosya yolu gerekli.")
            sys.exit(1)
        current_file_path = sys.argv[2]
    elif current_action == "--view-all":
        pass
    else:
         _show_startup_error(f"Hata: Geçersiz eylem '{current_action}'. Beklenen: --add, --view, --view-all")
         sys.exit(1)

    server_running = send_request_to_server(current_action, current_file_path)

    if server_running:
        sys.exit(0)
    else:
        print("Çalışan sunucu bulunamadı. Bu instance sunucu olacak...")
        start_server(initial_action=current_action, initial_file_path=current_file_path)
        print("Ana program sonlanıyor (start_server sonrası - beklenmedik durum).")
        sys.exit(0)