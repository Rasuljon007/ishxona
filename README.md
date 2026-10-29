# Ishxona

Tikuv ishxonasi uchun donabay ish haqi tizimi: Telegram bot va boshqaruv paneli (sayt).

- **Ishchi** botda qilgan ishini tanlab, sonini kiritadi va tasdiqlaydi. Bugungi ishlarini, shu oydagi oyligini va oylar tarixini ko'radi.
- **Boshqaruvchi (sardor)** o'z guruhidagi yozuvlarni tasdiqlaydi yoki rad etadi, ishchi nomidan ish kiritadi, brak kiritadi va kun yopilguncha (21:00) yozuvlarni izoh bilan tahrirlaydi.
- **Sardorlar sayti** (`/sardor/`): sardor telefon raqami va parol bilan kiradi, faqat o'z guruhini ko'radi, yozuvlarni tasdiqlaydi, rad etadi (sabab bilan) va kun yopilguncha izoh bilan tahrirlaydi. Ishchiga botda xabar boradi. Parolni boshliq panelda xodim sahifasidagi "sayt paroli" maydonida beradi.
- **Boshliq** botda istalgan davr bo'yicha hisobot va PDF oladi. Mahsulot, qism, narx, guruh va xodimlarni boshqaruv panelida (`/admin/`) boshqaradi.
- Har kuni soat 21:00 da har bir guruhning Telegram guruhiga PDF yuboriladi (faqat dona soni, summalarsiz). Boshliqqa esa tahrirlar hisoboti va summalar bilan umumiy PDF boradi. Soat 18:00 da ishini kiritmagan ishchilarga eslatma boradi.
- Bot o'zbek tilida ishlaydi, lotin va kirill yozuvini tanlash mumkin.

## Render'ga joylashtirish

1. render.com da **New → Blueprint** ni tanlang va shu repo'ni ulang. Render `render.yaml` faylidan baza va xizmatni o'zi yaratadi.
2. Render ikki qiymatni so'raydi:
   - `BOT_TOKEN`: @BotFather bergan token.
   - `ADMIN_PASSWORD`: boshqaruv paneli uchun parol (login: `boshliq`).
3. Joylashtirish tugagach, `https://<xizmat-nomi>.onrender.com/admin/` manziliga kiring.

## Birinchi sozlash (boshqaruv panelida)

1. **Xodimlar**: o'zingizni rol = Boshliq qilib, telefon raqamingiz bilan qo'shing. Boshqaruvchilarni ham qo'shing.
2. **Ishchi turlari**: Tikuvchi, Dazmolchi, Bichuvchi va boshqalar.
3. **Guruhlar**: masalan, "Tikuvchilar-1" va uning sardori.
4. **Mahsulotlar**: mahsulot va uning qismlari (ishchi turi va 1 dona narxi bilan). Tikish narxi avtomatik hisoblanadi.
5. Hamma botga `/start` yuborib, telefon raqamini jo'natadi. Ro'yxatda yo'q raqam bilan kirgan ishchi nofaol bo'lib qo'shiladi va boshliqqa xabar boradi. Uni panelda faollashtirib, guruh va ishchi turini belgilang.
6. Har bir guruh uchun Telegram guruh oching, botni qo'shing va o'sha guruhda `/ulash` buyrug'ini yuboring.

## Lokal ishga tushirish

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # qiymatlarni to'ldiring va eksport qiling
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver      # sayt
python manage.py runbot         # bot
python manage.py test           # testlar
```

## Demo ma'lumotlar

`python manage.py seed_demo` oxirgi ikki oy uchun demo yaratadi: ishchi turlari, 3 guruh va sardorlari, 23 ishchi, 4 mahsulot va qismlari, kunlik ish yozuvlari (tasdiqlangan, kutilayotgan, rad etilgan), brak, tahrirlar va narx o'zgarishlari. Demo xodimlarning telefoni `99800` bilan boshlanadi va ularda Telegram ID yo'q, shuning uchun bot ularga hech narsa yubormaydi. Qaytadan yaratish: `python manage.py seed_demo --reset`.

Botni turli rollarda sinash: botga `/start` yuborib, telefon raqamingizni jo'nating, keyin `python manage.py demo_rol sardor` (yoki `ishchi`, `boshliq`) ni ishga tushiring. Telegram hisobingiz o'sha roldagi demo xodimga o'tadi. Muayyan xodimni tanlash: `--kim Gulnora`.

## Tuzilma

- `core/models.py`: xodimlar, guruhlar, mahsulotlar, qismlar, ish yozuvlari, tahrirlar jurnali.
- `core/services.py`: barcha qoidalar (kuniga bitta yozuv, tasdiqlash, izohli tahrir, kunning yopilishi). Bot ham, sayt ham shu yerdan foydalanadi.
- `core/reports.py`: PDF hisobotlar.
- `bot/`: Telegram bot (aiogram 3) va kunlik rejalashtiruvchi.
