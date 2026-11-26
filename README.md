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

    python manage.py test apps

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

## Loglar

Xatolar `logs/errors.log` fayliga yoziladi (5 MB dan oshsa aylantiriladi,
5 ta eski fayl saqlanadi).

## Serverga joylash

Hali to'liq sozlanmagan: web server, proksi, statik fayllar,
loglarni boshqarish va zaxira nusxa keyin qo'shiladi.
