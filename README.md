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

Bu format DRF qayta ishlaydigan xatolarga tegishli. Mavjud bo'lmagan
manzil (404) va kutilmagan server xatosi (500) hozircha boshqa ko'rinishda.

## Loglar

Xatolar `logs/errors.log` fayliga yoziladi.

## Serverga joylash

Hali to'liq sozlanmagan: web server, proksi, statik fayllar,
loglarni boshqarish va zaxira nusxa keyin qo'shiladi.