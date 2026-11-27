# 3-bosqich hisoboti: login va xavfsizlik

**Sana:** 27.11.2026
**Holati:** tugadi. `python manage.py test` natijasi: **176 test, hammasi `OK`**.

## 1. Qisqa xulosa

3-bosqichning barcha 6 bandi bajarildi: ro'yxatdan o'tish va kirish,
email/telefon tasdiqlash va parol tiklash, sessiyalar va mobil token, ruxsatlarni
tekshirish, ota-ona va farzandni tasdiqlab bog'lash, xavfli so'rov va fayllarni
tekshirish. Loyiha endi veb (sessiya + CSRF) va mobil (Bearer token) mijozlarga
bir xil API orqali xizmat qila oladi.

## 2. Tekshiruv natijalari

| Buyruq | Natija |
|---|---|
| `python manage.py check` | Xato yo'q |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py test` | 176 test, `OK` (yangi qism qo'shilishidan oldin 113 ta edi, 63 ta qo'shildi) |
| `python manage.py spectacular --validate` | 0 xato, 3 ogohlantirish (`role` enum nomlari to'qnashuvi; hujjat to'g'ri chiqadi) |

Testlar bo'yicha:

| Guruh | Fayl | Nimani tekshiradi |
|---|---|---|
| Kirish va ro'yxatdan o'tish | `tests/accounts/test_auth_api.py` | register, login, logout, CSRF, cheklovlar |
| Tasdiqlash va tiklash | `tests/accounts/test_verification.py` | kodlar, urinishlar, kontakt o'zgarishi, parol tiklash |
| Mobil token | `tests/accounts/test_tokens.py` | token olish, muddat, qurilmalar, chiqish, limit |
| Ota-ona/farzand | `tests/family/test_family.py` | kod yaratish, qabul qilish, bekor qilish, ruxsat yordamchilari, baza cheklovlari |
| Fayl tekshiruvi | `tests/core/test_uploads.py` | kengaytma, signatura, Office fayllari, nomlar |
| So'rov xavfsizligi | `tests/core/test_requests.py` | JSON-only (415), hajm limiti (413) |

## 3. Bandlar bo'yicha bajarilgan ishlar

### 3.1 Ro'yxatdan o'tish, kirish, chiqish

- `/auth/register/`, `/auth/login/`, `/auth/logout/`, `/auth/me/`, `/auth/csrf/`.
- Login: `identifier` sifatida username, email yoki telefon.
- Parol Django qoidalari bilan tekshiriladi; maxsus huquq maydonlari
  (`is_staff` va h.k.) ro'yxatdan o'tishda e'tiborga olinmaydi.
- Xato javobi akkaunt bor-yo'qligini bildirmaydi.
- Cheklovlar: login IP bo'yicha 20/daqiqa va akkaunt bo'yicha 10/soat,
  ro'yxatdan o'tish IP bo'yicha 5/soat.

### 3.2 Email/telefon tasdiqlash va parol tiklash

- `VerificationCode`: 6 xonali kod, 10 daqiqa amal qiladi, bazada faqat HMAC xeshi.
- 5 marta xato kiritilsa kod yaroqsiz; yangi kod eskisini bekor qiladi;
  60 soniyada 1 ta va soatiga 5 tagacha kod.
- Kontakt o'zgarsa tasdiqlash bekor bo'ladi, eski kod yangi kontaktga o'tmaydi.
- Parol tiklash kodi faqat **tasdiqlangan** email/telefonga yuboriladi; javob
  akkaunt bor-yo'qligidan qat'i nazar bir xil (204).
- Parol tiklanganda veb sessiyalar va barcha mobil tokenlar yopiladi.
- Tashkilot taklifi faqat tasdiqlangan email/telefon bilan qabul qilinadi
  (2-bosqichdagi xavfsizlik cheklovi yopildi).

### 3.3 Mobil login va qurilmalar (Bearer token)

| Manzil | Usul | Vazifasi |
|---|---|---|
| `/auth/token/` | POST | Token olish (CSRF kerak emas) |
| `/auth/token/current/` | DELETE | Shu qurilmadan chiqish |
| `/auth/devices/` | GET | Kirgan qurilmalar (`is_current` bilan) |
| `/auth/devices/<id>/` | DELETE | Qurilmani chiqarish (faqat o'zingizniki) |
| `/auth/devices/revoke-all/` | POST | Barcha qurilmalardan chiqish |

- Token 256 bit tasodifiy, bazada faqat SHA-256 xeshi; xom token faqat olingan javobda ko'rinadi.
- 30 kun ishlatilmasa tugaydi; ishlatilsa uzayadi, lekin eng ko'pi 180 kun.
- Bir foydalanuvchida 10 tagacha qurilma; 11-si kirsa eng eskisi chiqariladi.
- O'chirilgan (`is_active=false`) foydalanuvchining tokeni ishlamaydi.
- Eskirgan token yuborilsa ham `/auth/token/` orqali yangidan kirish mumkin.
- Yaroqsiz token `403` (veb bilan bir xil); faqat `/auth/token/current/`
  `401` + `WWW-Authenticate: Bearer` qaytaradi.
- Login cheklovlari veb login bilan umumiy.

### 3.4 Kim qaysi ma'lumotni ko'rishi (ruxsatlar)

- 2-bosqichdagi rol va ruxsatlar tizimi (`apps/organizations/roles.py`) o'zgarmadi.
- Ota-onaning farzand ma'lumotiga huquqi uchun yagona tekshiruv nuqtasi:
  `apps.family.services.is_parent_of(parent, child)`, `children_of(user)`,
  `parents_of(user)`. Keyingi bosqichlarda ota-onaga farzand ma'lumotini
  ko'rsatishdan oldin **doim** shuni chaqirish kerak.
- Tashkilot rollari (`parent`, `student`) 6-7-bosqichda qo'shiladi.

### 3.5 Ota-ona va farzandni tasdiqlab bog'lash (`apps/family`)

| Manzil | Usul | Vazifasi |
|---|---|---|
| `/family/invites/` | GET, POST | Faol kodlarim; yangi kod yaratish |
| `/family/invites/<id>/` | DELETE | Kodni bekor qilish |
| `/family/links/accept/` | POST | Kodni kiritib bog'lash |
| `/family/links/` | GET | Bog'langan farzandlar va ota-onalar |
| `/family/links/<id>/` | DELETE | Bog'lanishni bekor qilish |

- Ikki tomon roziligi: bir tomon kod yaratadi, ikkinchisi o'z akkauntidan kiritadi.
- Kod 8 belgi, 24 soat, bir martalik, bazada HMAC xeshi, faqat yaratilganda ko'rinadi.
- Bir foydalanuvchida 5 tagacha faol kod; kod yaratish 20/soat, kiritish 10/soat.
- **Ota-ona tomonida tasdiqlangan email yoki telefon shart**; farzandda shart emas.
- O'zini o'ziga, ikki marta va teskari yo'nalishda bog'lab bo'lmaydi (bazada ham cheklov).
- Bekor qilingan bog'lanish o'chirilmaydi (`revoked_at`, kim bekor qilgani saqlanadi).
- Ikkinchi tomon haqida faqat `id`, `username`, ism va familiya ko'rinadi.
- Muhim amallar audit tarixiga yoziladi (`family.linked`, `family.unlinked` va h.k.).

### 3.6 Xavfli so'rovlar va fayllarni tekshirish

- API faqat JSON qabul qiladi (boshqa turga `415`). Fayl yuklaydigan view `MultiPartParser` ni o'zi qo'shadi.
- `RequestSizeLimitMiddleware`: `/api/` da JSON 1 MB, fayl so'rovi 12 MB dan oshsa `413`.
- `apps/core/uploads.py` — `validate_upload(file)`:
  - ruxsat: jpg, png, webp, pdf, docx, xlsx; 5 MB gacha;
  - kengaytma ro'yxatda va faylning boshidagi baytlar kengaytmaga mos bo'lishi shart;
  - `a.php.jpg`, SVG/HTML/skript, makroli Office fayli, buzuq yoki zip-bomba rad etiladi;
  - `storage_name()` diskka tasodifiy nom beradi (asl nom ishlatilmaydi).
- Sozlamalar: cookie `HttpOnly` va `SameSite=Lax`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin`.

## 4. Qabul qilingan qarorlar

- Mobil uchun bitta uzoq muddatli token (refresh token yo'q): oddiyroq, har qurilmadan bekor qilinadi.
- Ota-onaga tasdiqlangan kontakt talabi; farzandga yo'q (maktab o'quvchisida email/telefon bo'lmasligi mumkin). O'zgartirish: `_require_verified_parent` (`apps/family/services.py`).
- Bog'lash uchun kod (email/SMS emas): SMS provayderisiz ham ishlaydi va kim kimga bog'lanayotganini ikki tomon bilib turadi.
- Eski xatti-harakat saqlandi: kirmagan foydalanuvchiga `403`.

## 5. Ma'lum cheklovlar (ataylab qilinmagan)

- **Veb sessiyalar ro'yxati yo'q**: faqat mobil qurilmalar ko'rinadi.
- **Ikki bosqichli kirish (2FA) yo'q.**
- **Eski parolni bilib o'zgartirish manzili yo'q**: parol faqat tiklash orqali o'zgaradi.
- **SMS yuborilmaydi** (8-bosqich): `DEBUG=False` da telefonga kod `503` qaytaradi.
- Throttle hisobi hozircha jarayon xotirasida: server qayta ishga tushsa nolga tushadi, bir nechta jarayonda umumiy emas (9-bosqichda Redis).
- Rasm to'liq dekodlanmaydi (Pillow yo'q); antivirus tekshiruvi yo'q (9-bosqich).
- Hajm limiti `Content-Length` ga tayanadi; chunked so'rovni web server (`client_max_body_size`) cheklashi kerak (9-bosqich).
- Tiklash kodini boshqa odam 5 marta xato kiritib "yoqib" yuborishi mumkin (akkaunt egasi qayta so'raydi); throttling buni cheklaydi, to'liq yopmaydi.
- Parolni tiklash so'rovida email yuborish vaqti akkaunt bor-yo'qligini bildirishi mumkin; fon vazifalari (9-bosqich) buni yopadi.
- `spectacular` 3 ta enum nomi ogohlantirishini beradi (`role`); hujjat to'g'ri, lekin generatsiya qilingan mijoz kodida nomlar noqulay bo'lishi mumkin.
- Fayl yuklaydigan birinchi view (6-bosqich) `validate_upload()` ni chaqirishi shart.

## 6. Keyingi bosqichlarga ta'siri

- **4-bosqich (tarif/obuna):** foydalanuvchi va tashkilot tuzilmasi tayyor; to'lov amallari uchun `log_action` va throttle namunalaridan foydalaniladi.
- **6-7-bosqich:** `parent`/`student` rollari, farzand ma'lumotini ota-onaga ko'rsatishda `is_parent_of()`, fayl yuklashda `validate_upload()`.
- **8-bosqich:** SMS/email/push yetkazish (`apps/accounts/delivery.py` o'rniga umumiy xizmat).
- **9-bosqich:** Redis (throttle), web server limitlari, antivirus, fon vazifalari.

## 7. Keyingi qadam

4-bosqich: tariflar, 14 kunlik sinov, oylik/yillik obunalar, hisob-faktura va to'lovlar.
