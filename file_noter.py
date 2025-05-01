import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext
import sys
import os
import sqlite3
import ctypes # Windows Başlık Çubuğu Rengini Ayarlamak için (Opsiyonel)

# --- Ayarlar ---
# Notların saklanacağı veritabanı dosyasının yeri
# Kullanıcının AppData/Roaming klasöründe saklamak daha iyidir
APP_DATA_PATH = os.path.join(os.getenv('APPDATA'), 'FileNoter')
DB_PATH = os.path.join(APP_DATA_PATH, 'filenotes.db')
# ----------------

# Uygulama veri klasörünü oluştur
os.makedirs(APP_DATA_PATH, exist_ok=True)

# --- Veritabanı İşlemleri ---
def init_db():
    """Veritabanını ve tabloyu oluşturur (eğer yoksa)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                file_path TEXT PRIMARY KEY,
                note_text TEXT
            )
        ''')
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        show_error(f"Veritabanı hatası: {e}\nVeritabanı yolu: {DB_PATH}")
        sys.exit(1) # Kritik hata, çık

def save_note(file_path, note_text):
    """Belirli bir dosya yolu için notu kaydeder veya günceller."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # INSERT OR REPLACE: Varsa üzerine yazar, yoksa ekler
        cursor.execute("INSERT OR REPLACE INTO notes (file_path, note_text) VALUES (?, ?)",
                       (file_path, note_text))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        show_error(f"Not kaydedilirken hata oluştu: {e}")
        return False

def get_note(file_path):
    """Belirli bir dosya yolu için notu getirir."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT note_text FROM notes WHERE file_path = ?", (file_path,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else "" # Not yoksa boş string döner
    except sqlite3.Error as e:
        show_error(f"Not okunurken hata oluştu: {e}")
        return "" # Hata durumunda da boş dönelim

def delete_note(file_path):
    """Belirli bir dosya yolu için notu siler (Gelecekte eklenebilir)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notes WHERE file_path = ?", (file_path,))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        show_error(f"Not silinirken hata oluştu: {e}")
        return False

# --- GUI İşlemleri ---
def show_add_note_dialog(file_path):
    """Not ekleme/düzenleme penceresini gösterir."""
    root = tk.Tk()
    root.withdraw() # Ana pencereyi gizle, sadece diyalog görünsün

    # Windows 10/11 Koyu Tema için Başlık Çubuğu Ayarı (Opsiyonel)
    try:
        HWND = ctypes.windll.user32.GetParent(root.winfo_id())
        if HWND: # Eğer bir üst pencere varsa (genelde olur)
             # Değer: 19 (Windows 10 1903+) veya 20 (Windows 11 21H2+)
             # Koyu tema için 20, açık tema için 0 kullanmayı deneyin.
             # Bu her zaman çalışmayabilir ve Windows versiyonuna bağlıdır.
            value = 20
            ctypes.windll.dwmapi.DwmSetWindowAttribute(HWND, value, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int))
    except Exception:
        pass # Başarısız olursa önemli değil

    # Var olan notu al
    current_note = get_note(file_path)

    # Özel diyalog penceresi (Çok satırlı giriş için)
    dialog = tk.Toplevel(root)
    dialog.title(f"'{os.path.basename(file_path)}' için Not")
    dialog.geometry("400x300") # Boyut ayarla
    dialog.minsize(300, 200)  # Minimum boyut

    # Pencereyi ekranda ortala
    dialog.update_idletasks() # Pencere boyutunu hesaplamak için gerekli
    width = dialog.winfo_width()
    height = dialog.winfo_height()
    x = (dialog.winfo_screenwidth() // 2) - (width // 2)
    y = (dialog.winfo_screenheight() // 2) - (height // 2)
    dialog.geometry(f'{width}x{height}+{x}+{y}')

    # Etiket
    label = tk.Label(dialog, text=f"'{os.path.basename(file_path)}' dosyası için notunuzu girin:")
    label.pack(pady=(10, 5))

    # Çok satırlı metin alanı
    text_area = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, height=10, width=40)
    text_area.pack(expand=True, fill="both", padx=10, pady=5)
    text_area.insert(tk.INSERT, current_note)
    text_area.focus_set() # Açılır açılmaz metin alanına odaklan

    # Kaydetme fonksiyonu
    def on_save():
        new_note = text_area.get("1.0", tk.END).strip() # Başındaki/sonundaki boşlukları temizle
        if save_note(file_path, new_note):
            # Başarılı olursa (isteğe bağlı mesaj)
            # messagebox.showinfo("Başarılı", "Not kaydedildi.", parent=dialog)
            pass
        dialog.destroy() # Kaydettikten sonra pencereyi kapat
        root.quit() # Ana Tkinter döngüsünü bitir

    # Kaydet Butonu
    save_button = tk.Button(dialog, text="Kaydet", command=on_save)
    save_button.pack(pady=(5, 10))

    # Pencere kapatıldığında da ana döngüyü bitir
    dialog.protocol("WM_DELETE_WINDOW", lambda: (dialog.destroy(), root.quit()))

    # Enter tuşuna basıldığında kaydetmeyi dene (Ctrl+Enter daha güvenli olabilir)
    # dialog.bind('<Return>', lambda event=None: on_save()) # Tek satır hissi verir
    dialog.bind('<Control-Return>', lambda event=None: on_save()) # Ctrl+Enter ile kaydet

    root.mainloop() # Tkinter olay döngüsünü başlat

def show_view_note_dialog(file_path):
    """Notu görüntüleme penceresini gösterir."""
    root = tk.Tk()
    root.withdraw() # Ana pencereyi gizle

    note_text = get_note(file_path)
    file_name = os.path.basename(file_path)

    if not note_text:
        messagebox.showinfo(f"'{file_name}' için Not", f"Bu dosya için kayıtlı bir not bulunamadı.", parent=root)
    else:
        # Notu göstermek için basit bir bilgi kutusu yerine Toplevel kullanabiliriz
        dialog = tk.Toplevel(root)
        dialog.title(f"'{file_name}' Notu")
        dialog.geometry("400x300")
        dialog.minsize(300, 200)

        # Pencereyi ekranda ortala
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'{width}x{height}+{x}+{y}')

        text_area = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, height=10, width=40)
        text_area.pack(expand=True, fill="both", padx=10, pady=10)
        text_area.insert(tk.INSERT, note_text)
        text_area.config(state=tk.DISABLED) # Sadece okunabilir yap

        close_button = tk.Button(dialog, text="Kapat", command=dialog.destroy)
        close_button.pack(pady=10)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    root.mainloop() # Tkinter olay döngüsünü başlat (messagebox için de gerekli)


def show_error(message):
    """Genel bir hata mesajı gösterir."""
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("FileNoter Hatası", message, parent=root)
    root.quit()

# --- Ana Çalıştırma Bloğu ---
if __name__ == "__main__":
    init_db() # Her çalıştığında veritabanını kontrol et/oluştur

    # Komut satırı argümanlarını kontrol et
    # Beklenen format: python file_noter.py <eylem> <dosya_yolu>
    # Eylemler: --add, --view
    if len(sys.argv) < 3:
        show_error("Hata: Eksik komut satırı argümanları.\n\n"
                   "Bu betik doğrudan çalıştırılmak için değildir.\n"
                   "Windows sağ tık menüsü entegrasyonu ile kullanılmalıdır.")
        sys.exit(1)

    action = sys.argv[1]
    file_path = sys.argv[2] # Dosya yolu argümanını al

    # Dosya yolunun geçerli olup olmadığını kontrol et (isteğe bağlı ama iyi)
    if not os.path.exists(file_path):
         # Bazen sanal veya geçici dosyalar için bu olabilir, yine de devam etmeyi deneyebiliriz.
         # Ancak, silinmiş bir dosya ise notu göstermenin/eklemenin anlamı yok.
         # Şimdilik sadece bir uyarı verelim veya hata ile çıkalım.
         # show_error(f"Hata: Belirtilen dosya bulunamadı:\n{file_path}")
         # sys.exit(1)
         # Veya sadece devam et, veritabanı zaten yolu saklayacak.
         pass


    if action == "--add":
        show_add_note_dialog(file_path)
    elif action == "--view":
        show_view_note_dialog(file_path)
    else:
        show_error(f"Hata: Geçersiz eylem belirtildi: {action}\n"
                   "Beklenen: --add veya --view")
        sys.exit(1)