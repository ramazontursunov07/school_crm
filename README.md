# School CRM — Backend

Django 5.2, Django REST Framework, PostgreSQL.

## Ishga tushirish (Windows CMD)

1. Virtual muhit va kutubxonalar:

       python -m venv .venv
       .venv\Scripts\activate
       python -m pip install -r requirements.txt

2. PostgreSQL'da foydalanuvchi va baza yarating.
   `CREATEDB` huquqi faqat lokal testlar uchun kerak.

3. `.env.example` faylidan `.env` yarating:

       copy .env.example .env

   - `DJANGO_SECRET_KEY`: uzun tasodifiy qiymat. Yaratish:
     `python -c "import secrets; print(secrets.token_urlsafe(50))"`
   - `DJANGO_DEBUG`: kompyuterda `True`, serverda `False`.
   - `DB_NAME`, `DB_USER`, `DB_PASSWORD`: baza ma'lumotlari.

4. Ishga tushirish:

       python manage.py migrate
       python manage.py createsuperuser
       python manage.py runserver

## Testlar

    python manage.py test

## Manzillar

- Admin panel: `/admin/`
- API holati: `/api/v1/health/`
- API hujjati: `/api/v1/docs/` (`DEBUG=False` bo'lsa, faqat admin uchun)

## API qoidalari

- Barcha API manzillari `/api/v1/` bilan boshlanadi va `/` bilan tugaydi.
- Ma'lumot JSON formatida almashiladi.
- Maydon nomlari `snake_case` ko'rinishida: `first_name`.
- Sana va vaqt ISO 8601 formatida.
- API odatda faqat tizimga kirgan foydalanuvchiga ochiq.
  Ochiq manzillar kodda alohida belgilanadi.
- Hozir sessiya orqali autentifikatsiya ishlatiladi.
  Mobil ilova uchun login usuli 3-bosqichda tanlanadi.
- DRF'ning standart ro'yxat ko'rinishlari 20 tadan sahifalanadi.
  Javobda `count`, `next`, `previous`, `results` bo'ladi.

### Xato formati

```json
{
  "error": {
    "code": "validation_error",
    "message": "Yuborilgan ma'lumotlarda xato bor.",
    "details": {"phone": ["Bu maydon majburiy."]}
  }
}
```

Xuddi shu format `/api/` manzillaridagi 400, 403, 404 va 500 xatolariga ham
qo'llanadi (`details` u yerda `null`). `/api/` dan tashqari manzillarda
(masalan admin) Django'ning standart sahifasi chiqadi.

## Kirish (autentifikatsiya)

| Manzil | Usul | Vazifasi |
|---|---|---|
| `/auth/csrf/` | GET | CSRF token olish |
| `/auth/register/` | POST | `username`, `password`, `email` yoki `phone` |
| `/auth/login/` | POST | `identifier` (login, email yoki telefon), `password` |
| `/auth/logout/` | POST | Chiqish |
| `/auth/me/` | GET | Joriy foydalanuvchi (`email_verified`, `phone_verified` bilan) |
| `/auth/verify/request/` | POST | `channel` (`email` yoki `phone`): akkauntdagi kontaktga kod yuborish |
| `/auth/verify/confirm/` | POST | `channel`, `code`: kontaktni tasdiqlash |
| `/auth/password-reset/request/` | POST | `identifier`: tiklash kodini yuborish (javob doim 204) |
| `/auth/password-reset/confirm/` | POST | `identifier`, `code`, `new_password`: yangi parol o'rnatish |

- Barcha POST so'rovlarda `X-CSRFToken` sarlavhasi kerak. Login va
  ro'yxatdan o'tish javobida yangi token qaytadi.
- Cheklovlar: login IP bo'yicha 20/daqiqa va bitta akkaunt uchun 10/soat
  (muvaffaqiyatli urinishlar ham hisoblanadi); ro'yxatdan o'tish IP bo'yicha
  5/soat (xato so'rovlar ham hisoblanadi). Hisob jarayon xotirasida turadi:
  server qayta ishga tushsa nolga tushadi, bir nechta jarayonda umumiy emas.

### Email/telefon tasdiqlash va parolni tiklash

- Kod 6 xonali, 10 daqiqa amal qiladi, bazada faqat HMAC xeshi saqlanadi.
  5 marta xato kiritilsa kod yaroqsiz bo'ladi. Yangi kod so'ralsa, eskisi
  yaroqsiz. Bir akkauntga 60 soniyada 1 ta (`429` + `Retry-After`) va soatiga
  5 tagacha kod yuboriladi.
- Kontakt (email/telefon) o'zgarsa, tasdiqlash bekor bo'ladi va eski kod
  yangi kontaktni tasdiqlay olmaydi.
- Parolni tiklash kodi faqat **tasdiqlangan** email/telefonga yuboriladi.
  Akkaunt bormi-yo'qmi, tasdiqlanganmi-yo'qmi, javob bir xil (204).
  `identifier` login bo'lsa, avval tasdiqlangan email, bo'lmasa telefon ishlatiladi.
- Parol almashgach boshqa qurilmalardagi sessiyalar tugaydi.
- Email lokalda konsolga chiqadi (`EMAIL_BACKEND`); serverda SMTP sozlamalari
  `.env` da. **SMS provayderi hali ulanmagan** (8-bosqich): `DEBUG=True` da kod
  logga yoziladi, `DEBUG=False` da telefonga kod yuborish `503` qaytaradi.
  Telefon bilan tiklash/tasdiqlash shu paytgacha serverda ishlamaydi.
- Cheklovlar (xotirada, 9-bosqichgacha): tiklash so'rovi IP bo'yicha 10/soat va
  akkaunt bo'yicha 10/soat; kod so'rash IP bo'yicha 10/soat; taklif tokenini
  qabul qilish foydalanuvchi bo'yicha 10/soat.

## Tashkilotlar (SaaS)

Har bir o'quv markazi yoki maktab alohida **tashkilot**. Tashkilot ma'lumotlari
URL dagi `org_id` orqali ajratiladi: `/api/v1/organizations/<org_id>/...`

| Manzil | Usul | Vazifasi |
|---|---|---|
| `/organizations/` | GET, POST | Mening tashkilotlarim; yangi tashkilot yaratish |
| `/organizations/<org_id>/` | GET, PATCH | Tashkilot ma'lumoti |
| `/organizations/<org_id>/branches/` | GET, POST | Filiallar |
| `/organizations/<org_id>/branches/<id>/` | GET, PATCH | Filial (o'chirilmaydi, `is_active=false` qilinadi) |
| `/organizations/<org_id>/members/` | GET | Xodimlar |
| `/organizations/<org_id>/members/<id>/` | GET, PATCH | Rol, filial, faollikni o'zgartirish |
| `/organizations/<org_id>/invitations/` | GET, POST | Xodimni taklif qilish |
| `/organizations/<org_id>/invitations/<id>/` | DELETE | Taklifni bekor qilish |
| `/invitations/accept/` | POST | Taklifni qabul qilish (`{"token": "..."}`) |
| `/organizations/<org_id>/audit-logs/` | GET | Harakatlar tarixi (`?action=` bilan saralash) |

Qoidalar:

- Foydalanuvchi tashkilot a'zosi bo'lmasa, javob **404** (tashkilot bor-yo'qligi
  ham bildirilmaydi). A'zo bo'lsa-yu, ruxsati yo'q bo'lsa — **403**.
- Bir foydalanuvchi bir nechta tashkilotda, har birida alohida rol bilan ishlaydi.
- Yangi tashkilotni yaratgan foydalanuvchi `owner` bo'ladi, "Asosiy filial"
  avtomatik yaratiladi.
- Taklifni faqat taklifdagi email/telefonni **tasdiqlagan** foydalanuvchi qabul
  qila oladi.
- Taklif tokeni faqat taklif yaratilgan javobda ko'rinadi (bazada xeshi
  saqlanadi), 7 kun amal qiladi. Email/SMS orqali yuborish 8-bosqichda.
- Xodim o'zi bilan teng yoki yuqori rolli xodimni boshqara olmaydi va shunday
  rol bera olmaydi. Faqat `owner` hammani boshqaradi. O'z huquqini o'zgartirib
  bo'lmaydi. Faol `owner` kamida bitta qoladi.
- Ruxsatlar kodda: `apps/organizations/roles.py`.

| Rol | Ko'rish | Filial | Xodim taklif/boshqarish | Tashkilot sozlamasi | Harakatlar tarixi |
|---|---|---|---|---|---|
| `owner` | + | + | + | + | + |
| `director` | + | + | + | – | + |
| `admin` | + | + | + (faqat pastroq rollar) | – | – |
| `accountant`, `teacher` | + | – | – | – | – |

Tashkilotga tegishli yangi view yozishda `OrganizationScopedMixin`
(`apps/organizations/permissions.py`) ishlatiladi va ma'lumot doim
`self.organization` bo'yicha filtrlanadi. Muhim amallar
`apps.audit.services.log_action` bilan tarixga yoziladi.

## Tariflar (obuna)

CRM tariflari `apps/billing` da. Tarifni **faqat platforma admini** yaratadi
va o'zgartiradi (`/admin/` > Billing > Plans). Tarif hech qachon o'chirilmaydi:
sotuvdan olish uchun "sotuvda" belgisi o'chiriladi.

| Manzil | Usul | Vazifasi |
|---|---|---|
| `/billing/plans/` | GET | Sotuvdagi ochiq tariflar (kirish shart emas). `?organization_type=learning_center` bilan saralanadi |
| `/billing/plans/<code>/` | GET | Bitta tarif (kod bo'yicha) |

- Pul qiymatlari satr sifatida qaytadi (`"99000.00"`), valyuta alohida (`currency`).
- `price_yearly` bo'sh (`null`) bo'lsa, tarif yillik sotilmaydi.
  `yearly_discount_percent`: yillik to'lov 12 oylikdan necha foiz arzon (pastga yaxlitlanadi).
- `limits`: filial, xodim va o'quvchilar soni; `null` = cheksiz.
  Hozircha faqat e'lon qilinadi, majburlash 4-bosqichning "cheklash" qadamida.
- `features`: `{kalit: true/false}`. Ruxsat etilgan kalitlar ro'yxati
  `apps/billing/features.py` da (yangi kalit qo'shish uchun migratsiya kerak emas).
- Ochiq bo'lmagan (`is_public=false`) yoki sotuvdan olingan tarif ro'yxatda ham,
  kod bo'yicha ham ko'rinmaydi (404).
- Boshlang'ich **namuna** tariflar: `python manage.py seed_plans`
  (mavjudiga tegmaydi). Narxlar haqiqiy emas, admin panelda o'zgartiring.

### Sinov davri (14 kun)

Tashkilot tanlangan tarifni shu tarifning haqiqiy imkoniyat va cheklovlari bilan
sinaydi. Muddat tarifdagi `trial_days` dan olinadi (odatda 14, `0` = sinov yo'q).

| Manzil | Usul | Kim | Vazifasi |
|---|---|---|---|
| `/organizations/<org_id>/subscription/` | GET | egasi, direktor, hisobchi | Joriy obuna va `trial_available` |
| `/organizations/<org_id>/subscription/trial/` | POST | faqat egasi | Sinov boshlash: `{"plan": "standard"}` |

- Sinovni boshqarish (boshlash) faqat tashkilot egasida, ko'rish direktor va hisobchida
  ham (`billing.view`, `billing.manage`: `apps/organizations/roles.py`).
- Tashkilot sinovdan umri davomida **bir marta** foydalanadi (bazada ham cheklangan),
  tugagandan keyin qayta boshlab bo'lmaydi. Bitta foydalanuvchi ko'pi bilan 3 ta sinov
  boshlay oladi (`MAX_TRIALS_PER_USER`, `apps/billing/services.py`).
- Muddatni mijoz belgilay olmaydi: u serverda hisoblanadi.
- Holat vaqt bo'yicha hisoblanadi: sinov muddati o'tgach, javobda darhol `expired`
  chiqadi. Bazadagi holatni yangilash uchun muddatida ishga tushiring:
  `python manage.py expire_trials` (9-bosqichda jadvalga qo'yiladi).
- Xatolar (`error.code`): `trial_active`, `trial_already_used`, `trial_limit_reached`
  (409); noto'g'ri tarif uchun 400 (`details.plan`).

## Loglar

Xatolar `logs/errors.log` fayliga yoziladi (5 MB dan oshsa aylantiriladi,
5 ta eski fayl saqlanadi).

## Serverga joylash

Hali to'liq sozlanmagan: web server, proksi, statik fayllar,
loglarni boshqarish va zaxira nusxa keyin qo'shiladi.
