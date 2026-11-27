# 3-bosqich hisoboti: login va xavfsizlik (QISMAN)

**Sana:** 26.11.2026

## Qisqa xulosa

Ro'yxatdan o'tish, kirish/chiqish, email/telefon tasdiqlash, parolni tiklash
va taklifni faqat tasdiqlangan kontakt bilan qabul qilish yozildi.
Mobil login, ota-ona/farzand bog'lash va fayl tekshiruvi hali qilinmagan.

Testlar **ishga tushirildi**.

## Bandlar holati

| Band | Holati | Izoh |
|---|---|---|
| Ro'yxatdan o'tish, kirish va chiqish | Bajarilgan (avval) | Sessiya + CSRF, throttling |
| Email/telefonni tasdiqlash | Yozildi, testlanmagan | `VerificationCode`, `/auth/verify/*` |
| Parolni tiklash | Yozildi, testlanmagan | Faqat tasdiqlangan kontaktga |
| Sessiyalar va qo'shimcha xavfsizlik | Qisman | Parol almashganda sessiyalar tugaydi. Mobil token va qurilmalar ro'yxati yo'q |
| Kim qaysi ma'lumotni ko'rishi | Qisman | 2-bosqichdagi rollar. Ota-ona/o'quvchi rollari yo'q |
| Ota-ona va farzandni bog'lash | Qilinmagan | |
| Xavfli so'rovlar va fayllarni tekshirish | Qilinmagan | Taklif tokeni uchun throttling qo'shildi, fayl yuklash hali yo'q |

## Bajarilgan ishlar

- `User`: `email_verified_at`, `phone_verified_at`. Kontakt o'zgarsa belgi bekor bo'ladi.
- `VerificationCode` modeli (migratsiya `0002_verification`). Kod xom holda saqlanmaydi.
- Kod qoidalari: 10 daqiqa, 5 urinish, 60 soniya kutish, soatiga 5 ta.
- `accept_invitation` endi faqat tasdiqlangan email/telefonni hisobga oladi
  (2-bosqich hisobotidagi xavfsizlik cheklovi yopildi).
- Taklif tokenini sinab ko'rishdan himoya: foydalanuvchi bo'yicha 10/soat.
- Email `EMAIL_BACKEND` orqali; SMS uchun joy (`delivery.py`) tayyor.

## Ma'lum cheklovlar

- **SMS yuborilmaydi** (8-bosqich). `DEBUG=False` da telefon kodi `503` qaytaradi.
- Tiklash kodini boshqa odam 5 marta xato kiritib "yoqib" yuborishi mumkin
  (akkaunt egasi qayta so'raydi). Throttling buni cheklaydi, to'liq yopmaydi.
- Parolni tiklash so'rovida email yuborish vaqti akkaunt bor-yo'qligini
  bildirishi mumkin (javob matni bir xil). Fon vazifalari (9-bosqich) buni yopadi.
- Throttle hisobi xotirada (9-bosqichda Redis).
- Mobil ilova uchun login usuli hali tanlanmagan/qilinmagan.

## Tekshiruv (sizda ishga tushiring)

| Buyruq | Kutiladi |
|---|---|
| `python manage.py check` | Xato yo'q |
| `python manage.py makemigrations --check --dry-run` | `No changes detected`. Migratsiya qo'lda yozilgan, shu yerda farq chiqsa `makemigrations` ishlating |
| `python manage.py migrate` | `0002_verification` qo'llanadi |
| `python manage.py test` | Hammasi `OK` (70 tadan keyin ~30 ta yangi test) |
| `python manage.py spectacular --validate` | Xato yo'q |

## Keyingi qadamlar

Mobil login (qurilma tokenlari), ota-ona/farzand bog'lash, fayl tekshiruvi.
