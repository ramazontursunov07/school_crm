# 1-bosqich hisoboti: backend asosini tayyorlash

**Sana:** 26.11.2026

## Qisqa xulosa

Backend asosi tayyorlandi. Oldindan yozilgan Django kodi bo'lmagani uchun
loyiha noldan boshlandi. Serverga joylash va zaxira nusxa hali qilinmagan.

## Bandlar holati

| Band | Holati | Izoh |
|---|---|---|
| Mavjud Django kodini tekshirish va saqlash | Talab qilinmadi | Eski kod yo'q. Yangi kod Git va GitHub'da saqlanadi |
| PostgreSQL bazasini tartibga keltirish | Bajarildi (lokal) | Alohida baza va foydalanuvchi yaratildi |
| Dastur modullarini ajratish | Boshlang'ich qismi bajarildi | `accounts` va `core`; qolganlari o'z bosqichida qo'shiladi |
| Frontend va mobil uchun API qoidalari | Asosi bajarildi | Qoidalar `README.md` faylida |
| Test, server sozlamalari va xatolarni qayd qilish | Qisman bajarildi | Testlar va loglar tayyor; serverga joylash qolgan |

## Bajarilgan ishlar

- Django 5.2.19 loyihasi yaratildi (Python 3.14.3, PostgreSQL 18.4).
- Maxfiy sozlamalar `.env` fayliga chiqarildi, namuna sifatida
  `.env.example` qo'shildi. `.env` GitHub'ga yuklanmaydi.
- O'z foydalanuvchi modeli yaratildi (`email` va `phone` takrorlanmaydi).
- Django REST Framework ulandi, API manzillari `/api/v1/` bilan boshlanadi.
- Swagger orqali API hujjati qo'shildi.
- Sahifalash (20 tadan) va DRF xatolari uchun yagona format sozlandi.
- API holatini tekshiradigan `/api/v1/health/` manzili qo'shildi.
- Xatolar `logs/errors.log` fayliga yoziladigan qilib sozlandi.
- `DEBUG=False` holati uchun asosiy HTTPS sozlamalari qo'shildi.
- `README.md` yozildi.

## Tekshiruv natijalari

GitHub'dan olingan toza nusxada, yangi virtual muhitda (mavjud `.env`
va lokal PostgreSQL bilan):

| Buyruq | Natija |
|---|---|
| `python manage.py check` | Xato topilmadi |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py test apps` | 7 ta test, `OK` |

Testlar quyidagilarni tekshiradi:

- `health` manzili javobi va noto'g'ri so'rovdagi xato formati (2 ta);
- parol xeshlanishi, email va telefonning tartibga keltirilishi,
  bo'sh qiymatlar va takrorlanmaslik (5 ta).

Asosiy loyihada admin panelga kirish, `/api/v1/health/` va `/api/v1/docs/`
sahifalari brauzerda tekshirildi.

Xatoning log fayliga yozilishi alohida sinov loyihasida tekshirildi.
HTTPS sozlamalari haqiqiy serverda hali sinalmagan.

## Qolgan ishlar

- Serverga joylash: web server, proksi, statik fayllar, loglarni boshqarish.
- Zaxira nusxa olish va qayta tiklashni sozlash.
- 404 va 500 xatolarini yagona API formatiga keltirish.
- Telefon raqami formatini tekshirish (3-bosqich).
- Mobil ilova uchun login usulini tanlash (3-bosqich).

## Keyingi bosqich

2-bosqich: SaaS tashkilotlar tizimi (tashkilotlar, filiallar, rollar va
ruxsatlar, ma'lumotlarni bir-biridan himoyalash, xodimlarni taklif qilish,
harakatlar tarixi).
