"""All bot texts, written in Latin script and transliterated on the fly for Cyrillic users."""

import html

from core.translit import to_cyrillic

TEXTS = {
    # registration
    "choose_script": "Yozuvni tanlang:",
    "ask_contact": "Assalomu alaykum! Ro'yxatdan o'tish uchun pastdagi tugma orqali telefon raqamingizni yuboring.",
    "send_contact": "Telefon raqamni yuborish",
    "own_contact_only": "Iltimos, o'zingizning raqamingizni tugma orqali yuboring.",
    "registered_wait": "Ro'yxatga olindingiz. Boshliq hisobingizni faollashtirgach, botdan foydalanishingiz mumkin bo'ladi.",
    "not_active": "Hisobingiz hali faollashtirilmagan. Boshliqqa murojaat qiling.",
    "not_registered": "Avval ro'yxatdan o'ting: /start",
    "welcome": "Xush kelibsiz, {name}! Kerakli bo'limni tanlang.",
    "new_worker_for_boss": "Yangi ishchi ro'yxatdan o'tdi: <b>{name}</b>, {phone}. Admin panelda uni faollashtiring, guruh va ishchi turini belgilang.",
    "script_saved": "Saqlandi.",
    # menu buttons
    "btn_enter": "Ish kiritish",
    "btn_my_today": "Bugungi ishlarim",
    "btn_my_month": "Oyligim",
    "btn_history": "Oylar tarixi",
    "btn_script": "Lotin / Kirill",
    "btn_pending": "Kutilayotganlar",
    "btn_enter_for": "Ishchi nomidan kiritish",
    "btn_edit": "Tahrirlash va brak",
    "btn_team_today": "Bugungi holat",
    "btn_rep_today": "Hisobot: bugun",
    "btn_rep_week": "Hisobot: shu hafta",
    "btn_rep_month": "Hisobot: shu oy",
    "btn_rep_range": "Hisobot: sana oralig'i",
    "yes": "Ha, tasdiqlayman",
    "no": "Yo'q, bekor qilish",
    "cancelled": "Bekor qilindi.",
    # entry flow
    "no_worker_type": "Sizga hali ishchi turi belgilanmagan. Boshliqqa murojaat qiling.",
    "no_products": "Siz uchun ish turlari hali kiritilmagan.",
    "choose_product": "Mahsulotni tanlang:",
    "choose_operation": "{product}: ish turini tanlang:",
    "all_entered": "Bu mahsulot bo'yicha bugungi barcha ishlar allaqachon kiritilgan.",
    "ask_quantity": "<b>{product} / {operation}</b> ({price})\nNechta tikdingiz? Sonini yozing:",
    "ask_quantity_for": "<b>{worker}</b>: {product} / {operation} ({price})\nNechta tikdi? Sonini yozing:",
    "bad_number": "Iltimos, faqat son yozing (masalan: 120).",
    "confirm_self": "Rostdan ham bugun <b>{product} / {operation}</b> ishidan <b>{qty} dona</b> tikkaningizni tasdiqlaysizmi?",
    "confirm_for": "<b>{worker}</b> uchun bugun <b>{product} / {operation}</b>: <b>{qty} dona</b> kiritilsinmi?",
    "sent_for_approval": "Yuborildi. Boshqaruvchi tasdiqlagach, oylikka qo'shiladi.",
    "entered_for": "Kiritildi va tasdiqlandi.",
    "choose_worker": "Ishchini tanlang:",
    "no_workers": "Guruhingizda faol ishchilar yo'q.",
    # notifications
    "new_entry": "Yangi yozuv: <b>{worker}</b>\n{product} / {operation}: <b>{qty} dona</b> ({amount})\nSana: {date}",
    "unusual": "Diqqat: bu son ishchining odatdagidan 2 baravardan ko'p.",
    "btn_approve": "Tasdiqlash",
    "btn_reject": "Rad etish",
    "approved_mark": "Tasdiqlandi ({by})",
    "rejected_mark": "Rad etildi ({by}): {reason}",
    "you_approved": "Yozuvingiz tasdiqlandi: {product} / {operation}, {qty} dona. Oylikka {amount} qo'shildi.",
    "you_rejected": "Yozuvingiz rad etildi: {product} / {operation}, {qty} dona.\nSabab: {reason}\nTo'g'rilab qayta kiritishingiz mumkin.",
    "entered_for_you": "{manager} siz uchun kiritdi: {product} / {operation}, {qty} dona ({amount}).",
    "edited_for_you": "{manager} yozuvingizni o'zgartirdi: {product} / {operation}, {field}: {old} → {new}.\nIzoh: {comment}",
    "ask_reject_reason": "Rad etish sababini yozing:",
    # manager
    "no_pending": "Kutilayotgan yozuvlar yo'q.",
    "pending_count": "Kutilayotgan yozuvlar: {count} ta.",
    "btn_approve_all": "Hammasini tasdiqlash ({count})",
    "approved_all": "{count} ta yozuv tasdiqlandi.",
    "no_editable": "Bugun o'zgartirish mumkin bo'lgan tasdiqlangan yozuvlar yo'q.",
    "choose_entry": "Qaysi yozuvni o'zgartirasiz?",
    "choose_field": "<b>{worker}</b>: {product} / {operation}\nSoni: {qty}, brak: {defect}\nNimani o'zgartirasiz?",
    "btn_field_qty": "Sonini o'zgartirish",
    "btn_field_defect": "Brak kiritish",
    "field_quantity": "soni",
    "field_defect_quantity": "brak",
    "ask_new_qty": "Yangi sonni yozing:",
    "ask_new_defect": "Brak sonini yozing (0 dan {max} gacha):",
    "ask_comment": "Izoh yozing (nima uchun o'zgartiryapsiz). Bu izoh boshliqqa hisobotda boradi:",
    "edit_saved": "O'zgartirildi: {field} {old} → {new}.",
    "team_status_head": "Bugungi holat ({date}):",
    "team_status_row": "{name}: tasdiqlangan {approved} dona, kutilmoqda {pending} dona",
    "team_missing": "Hali kiritmaganlar: {names}",
    # worker reports
    "my_today_empty": "Bugun hali hech narsa kiritmadingiz.",
    "my_today_head": "Bugungi ishlaringiz ({date}):",
    "my_today_row": "{product} / {operation}: {qty} dona, brak {defect} · {status}",
    "my_month": "<b>{start} – {end}</b>\nTasdiqlangan ish: {qty} dona, brak {defect}\nOylik (shu kungacha): <b>{amount}</b>",
    "my_month_pending": "Tasdiqlanishi kutilayotgan yozuvlar: {count} ta.",
    "history_empty": "Hali tasdiqlangan ishlaringiz yo'q.",
    "history_head": "Oylar bo'yicha:",
    "history_row": "{month}: {qty} dona, {amount}",
    "status_pending": "kutilmoqda",
    "status_approved": "tasdiqlangan",
    "status_rejected": "rad etilgan",
    # boss reports
    "ask_range": "Sana oralig'ini yozing, masalan: 01.10.2026 28.10.2026",
    "bad_range": "Sanalarni tushunmadim. Namuna: 01.10.2026 28.10.2026",
    "report_head": "<b>{period}</b>\nJami: {qty} dona, brak {defect}, ish haqi <b>{amount}</b>",
    "report_row": "{i}. {name} ({team}): {qty} dona, {amount}",
    "report_more": "To'liq ro'yxat PDF faylda.",
    # daily
    "daily_caption": "{team}: {date} kunlik hisobot",
    "daily_boss_caption": "{date}: umumiy hisobot (summalar bilan)",
    "edits_head": "{date}: boshqaruvchilar tahrirlari",
    "edits_none": "{date}: bugun tahrirlar bo'lmadi.",
    "edits_row": "{editor}: {worker}, {product} / {operation}, {field} {old} → {new} ({time}). Izoh: {comment}",
    "reminder": "Bugungi ishingizni kiritdingizmi? Soat {hour}:00 da kun yopiladi.",
    "manager_reminder": "Tasdiqlanmagan yozuvlar bor: {count} ta. Soat {hour}:00 gacha ko'rib chiqing.",
    # groups
    "bind_choose": "Bu Telegram guruhni qaysi ishchi guruhiga ulaymiz?",
    "bind_done": "Ulandi: {team}. Kunlik hisobotlar shu yerga yuboriladi.",
    "bind_no_rights": "Guruhni faqat boshliq yoki boshqaruvchi ulay oladi.",
    "use_private": "Bot bilan shaxsiy chatda ishlang.",
}


def t(key, script="latin", **kwargs):
    if kwargs:
        kwargs = {k: html.escape(v, quote=False) if isinstance(v, str) else v for k, v in kwargs.items()}
        text = TEXTS[key].format(**kwargs)
    else:
        text = TEXTS[key]
    return to_cyrillic(text) if script == "cyrillic" else text


def variants(key):
    """Both spellings of a button label, for matching incoming messages."""
    return {t(key, "latin"), t(key, "cyrillic")}


MENU_KEYS = [
    "btn_enter", "btn_my_today", "btn_my_month", "btn_history", "btn_script",
    "btn_pending", "btn_enter_for", "btn_edit", "btn_team_today",
    "btn_rep_today", "btn_rep_week", "btn_rep_month", "btn_rep_range",
]


def menu_texts():
    return set().union(*(variants(k) for k in MENU_KEYS))
