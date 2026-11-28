# 4-bosqich hisoboti: tarif va obunalar

**Holati:** jarayonda (1-2-qadamlar tugadi). Qadamlar birin-ketin bajariladi.
**Sinov:** `python manage.py test` natijasi: **261 test, hammasi `OK`**.

## Qadamlar holati

| # | Band | Holati |
|---|---|---|
| 1 | CRM tariflarini yaratish | **Bajarildi** |
| 2 | 14 kunlik haqiqiy sinov tizimi | **Bajarildi** |
| 3 | Oylik va yillik obunalar | Kutilmoqda |
| 4 | Hisob-faktura va to'lovlarni qayd etish | Kutilmoqda |
| 5 | To'lov xizmatlari bilan xavfsiz ulanish | Kutilmoqda |
| 6 | Obunani uzaytirish, bekor qilish va cheklash | Kutilmoqda |
| 7 | CRM obunasi bilan pullik e'lon to'lovlarini alohida yuritish | Kutilmoqda |

## 1-qadam: CRM tariflarini yaratish

### Nima qilindi

- Yangi `apps/billing` app va `Plan` modeli.
- Tarif maydonlari: kod, nom, tavsif, kimlar uchun (barcha turlar / o'quv markazi /
  xususiy maktab), valyuta, oylik va yillik narx, cheklovlar (filial, xodim,
  o'quvchi), imkoniyatlar (feature flag), sotuvda / ochiq ro'yxatda belgilari, tartib.
- Qoidalar baza darajasida ham tekshiriladi: kamida bitta narx bo'lishi shart,
  narx manfiy bo'lmaydi (`CheckConstraint`). Qolganlari (valyuta formati,
  imkoniyatlar kalitlari) `save()` da `full_clean()` bilan.
- Admin: imkoniyatlar JSON o'rniga belgilash katakchalari; `code` yaratilgandan
  keyin o'zgarmaydi; tarifni o'chirib bo'lmaydi; har yaratish/o'zgartirish
  `AuditLog` ga yoziladi (`billing.plan_created`, `billing.plan_updated`).
- Ochiq API: `GET /billing/plans/` va `GET /billing/plans/<code>/`
  (kirishsiz, IP bo'yicha 120/daqiqa).
- `python manage.py seed_plans`: 3 ta namuna tarif (Start, Standart, Pro).

### Qarorlar

- **Narx tarifda, lekin obuna uni nusxalab saqlaydi.** Tarif narxi o'zgarsa,
  mavjud obunachilar va eski hisob-fakturalar o'zgarmasligi kerak. Buni
  3-4-qadamlarda obuna va hisob-faktura modeli ta'minlaydi.
- **Pul `Decimal(14, 2)`**, API'da satr sifatida (float xatolari bo'lmasin).
- **Cheklovlar hozircha faqat e'lon qilinadi.** Majburlash (limitdan oshganda
  rad etish) 6-qadamda.
- **`is_public` va `is_active` alohida:** ochiq bo'lmagan, lekin sotuvdagi tarif
  alohida kelishuv (individual narx) uchun ishlatiladi.

### Tekshiruv natijalari

| Buyruq | Natija |
|---|---|
| `python manage.py check` | Xato yo'q |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py test` | 212 test, `OK` (176 eskisi + 36 yangi) |
| `python manage.py spectacular --validate` | 0 xato, 3 ogohlantirish (3-bosqichdagi bilan bir xil) |

Yangi testlar (`tests/billing/`): model qoidalari va baza cheklovlari (15),
ochiq API (12), admin va `seed_plans` (9).

### Ma'lum cheklovlar

- Namuna tariflarning narxi va cheklovlari haqiqiy biznes qarori emas.

## 2-qadam: 14 kunlik haqiqiy sinov

### Nima qilindi

- `Subscription` modeli: tashkilot, tarif, holat (`trialing` / `expired`), sinov
  boshlanishi va tugashi, kim boshlagani. Pullik obuna 3-qadamda shu modelga qo'shiladi.
- `Plan.trial_days` (odatda 14, `0` = sinov yo'q): sinov muddati tarifda turadi.
- API: `GET /organizations/<id>/subscription/` va
  `POST /organizations/<id>/subscription/trial/` (faqat egasi boshlaydi).
- Rollar: `billing.view` (egasi, direktor, hisobchi) va `billing.manage` (faqat egasi).
- `python manage.py expire_trials`: muddati o'tgan sinovlarni bazada `expired` qiladi
  va tarixga yozadi (`billing.trial_expired`). Boshlash ham tarixga yoziladi
  (`billing.trial_started`).
- Adminda obunalar ro'yxati (faqat ko'rish).

### "Haqiqiy" sinov degani

- **Bir tashkilot, bir sinov.** Bu qoida bazaning o'zida cheklangan
  (`one_trial_per_organization`); sinov tugagach ham qayta boshlab bo'lmaydi.
- **Bitta foydalanuvchi ko'pi bilan 3 ta sinov** boshlay oladi: ko'p tashkilot
  ochib, sinovni qayta-qayta olishga qarshi.
- **Muddatni mijoz belgilamaydi:** tugash vaqti serverda tarifdagi `trial_days` dan hisoblanadi.
- **Tugash vaqt bo'yicha aniqlanadi.** `expire_trials` kechiksa ham, muddatdan keyin
  javobda darhol `expired` chiqadi (holat bazaga keyinroq yoziladi).
- **Parallel so'rovlar:** tashkilot qatori qulflanadi va bazadagi cheklov ikkinchi
  sinovni baribir o'tkazmaydi.

### Qarorlar

- **Sinov tanlangan tarifga beriladi** (tarifning haqiqiy imkoniyat va cheklovlari bilan).
  Alohida "sinov tarifi" yaratilmadi.
- **Sinovni faqat egasi boshlaydi:** bu pul masalasiga olib boruvchi harakat.
- **Foydalanuvchi o'chirilsa**, uning boshlagan sinovlari hisobi bo'shaydi
  (`trial_started_by` bo'sh qoladi); tashkilot bo'yicha cheklov saqlanadi.
- **3 ta sinov chegarasi** va **14 kun** biznes qarori emas, namuna qiymatlar.

### Tekshiruv natijalari

| Buyruq | Natija |
|---|---|
| `python manage.py check` | Xato yo'q |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py test` | 261 test, `OK` (212 eskisi + 49 yangi) |
| `python manage.py spectacular --validate` | 0 xato, 3 ogohlantirish (avvalgi bilan bir xil) |

Yangi testlar: obuna modeli va baza cheklovlari (10), sinov API (23: boshlash,
tarif tekshiruvi, foydalanuvchi chegarasi, holat, ruxsatlar va izolyatsiya),
muddat tugashi va `expire_trials` (7), `trial_days` (4), billing rollari (3),
admin (2).

### Ma'lum cheklovlar

- Sinov hozircha **hech narsani cheklamaydi**: tarif limitlari va imkoniyatlari
  majburlanmaydi (6-qadam). Sinov tugagach ham tashkilot ishlashda davom etadi.
- Sinovni uzaytirish va bekor qilish yo'q (6-qadam).
- Sinov tugashi haqida email/SMS yuborilmaydi (8-bosqich).
- `expire_trials` jadvalga qo'yilmagan: hozircha qo'lda (9-bosqichda fon vazifasi).
