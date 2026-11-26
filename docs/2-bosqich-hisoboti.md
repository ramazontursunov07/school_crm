# 2-bosqich hisoboti: SaaS — tashkilotlar tizimi

**Sana:** 26.11.2026

## Qisqa xulosa

Tashkilotlar, filiallar, rollar, taklif va harakatlar tarixi backendda
tayyor va testlangan. Ma'lumotlar tashkilotlar o'rtasida ajratilgan.
Login, email/telefon tasdiqlash va obuna keyingi bosqichlarda, shu sababli
quyidagi **cheklovlar** bor (pastda "Ma'lum cheklovlar").

## Bandlar holati

| Band | Holati | Izoh |
|---|---|---|
| Har bir o'quv markazi/maktabga alohida hisob | Bajarildi | `Organization`, turi: o'quv markazi yoki xususiy maktab |
| Tashkilotlar va filiallar bazasi | Bajarildi | `Organization`, `Branch`; filial o'chirilmaydi, faolsizlantiriladi |
| Foydalanuvchilar, rollar va ruxsatlar | Bajarildi | 5 ta rol: owner, director, admin, accountant, teacher. Ota-ona va o'quvchi rollari 3 va 6–8-bosqichlarda |
| Bir foydalanuvchining bir nechta tashkilotda ishlashi | Bajarildi | `Membership` (har tashkilotda alohida rol) |
| Tashkilotlar ma'lumotlarini bir-biridan himoyalash | Bajarildi (kod darajasida) | A'zo bo'lmaganga 404; testlar bor. Baza darajasidagi himoya (RLS) qilinmagan |
| Xodimlarni taklif qilish | Bajarildi (qisman) | Token yaratiladi va qabul qilinadi; email/SMS yuborish 8-bosqichda |
| Harakatlar tarixini saqlash | Bajarildi | `AuditLog`, faqat qo'shiladi |

## Bajarilgan ishlar

- `apps/organizations`: modellar, rollar/ruxsatlar (`roles.py`), tashkilot
  doirasidagi ruxsat tekshiruvi (`permissions.py`), servislar, API.
- `apps/audit`: harakatlar tarixi modeli, `log_action` funksiyasi, o'qish API'si,
  adminda faqat ko'rish.
- Xavfsizlik qoidalari: taklif tokeni bazada xeshlanadi; rol berish va
  boshqarish faqat o'zidan pastroq rollar uchun; o'z huquqini o'zgartirib
  bo'lmaydi; oxirgi faol egani olib tashlab bo'lmaydi; boshqa tashkilot
  filialini biriktirib bo'lmaydi; ruxsati yo'q usullar yopiq (default deny).
- 1-bosqichdan qolganlar: `/api/` uchun 400/403/404/500 yagona JSON formati;
  `errors.log` aylantiriladi.
- Testlar uchun tezroq parol xeshlagich (faqat `manage.py test` paytida).
- README'ga API jadvali va rollar jadvali qo'shildi.

## Tekshiruv natijalari

Sinov muhiti: Python 3.12, PostgreSQL 16, Django 5.2 (sizdagi Python 3.14 /
PostgreSQL 18 emas).

| Buyruq | Natija |
|---|---|
| `python manage.py check` | Xato topilmadi |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py spectacular --validate` | Ogohlantirish va xato yo'q |
| `python manage.py test` | 70 ta test, `OK` (avval 7 ta edi) |

Yangi testlar: rollar (6), tashkilot va filial API (15), taklif (15),
xodimlarni boshqarish (10), tashkilotlarni ajratish va audit (11), xato
formati (4).

Testlar jarayonida ikkita haqiqiy xato topilib tuzatildi: qabul qilishda
`select_for_update` nullable filial bilan birga ishlamasligi; ruxsat
berilmagan usullar 405 o'rniga 403 qaytarishi.

## Ma'lum cheklovlar (keyingi bosqichlarga)

- **Taklifni qabul qilishda email/telefon tasdiqlanmagan qiymat bo'yicha
  solishtiriladi.** Kimdir boshqa odamning emailini kiritib ro'yxatdan
  o'tsa va tokenni qo'lga kiritsa, taklifni qabul qila oladi. 3-bosqichda
  tasdiqlash qo'shilganda `accept_invitation` faqat tasdiqlangan
  kontaktlarni hisobga olishi shart (kodda izoh bor).
- Tokenni sinab ko'rishdan himoya (throttling) hali yo'q, 3-bosqichda.
- Autentifikatsiya hozircha faqat sessiya; testlarda `force_authenticate`.
- Har kim yangi tashkilot yaratishi mumkin; tarif va sinov muddati 4-bosqichda.
- IP manzil `REMOTE_ADDR` dan olinadi; proksi ortida to'g'ri sozlash 9-bosqichda.
- Xodimning `branch` maydoni saqlanadi, lekin filial bo'yicha ma'lumotni
  cheklash hali yo'q (6-bosqichda guruh, to'lov va hokazo bilan birga).
- Yagona tashkilot egasi hisobini o'chirsa/tashkilotni yopish oqimi yo'q.
- Serverga joylash va zaxira nusxa 9-bosqichgacha qolgan.

## Keyingi bosqich

3-bosqich: login va xavfsizlik (ro'yxatdan o'tish, kirish/chiqish,
email/telefon tasdiqlash, parolni tiklash, mobil uchun login usuli,
ota-ona va farzand akkauntlarini bog'lash).
