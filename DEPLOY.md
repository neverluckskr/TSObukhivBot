# Деплой на Railway

## Быстрый старт

1. **Создайте проект на Railway**
   - Перейдите на [railway.app](https://railway.app)
   - Войдите через GitHub
   - Нажмите "New Project"
   - Выберите "Deploy from GitHub repo"
   - Выберите ваш репозиторий

2. **Настройте переменные окружения**

   В Railway Dashboard → Variables добавьте:

   ```
   BOT_TOKEN=ваш_токен_бота
   CHANNEL_ID=-1003595248840
   MODERATORS=1716175980,751886453,6581301275,7038303400,1217658419
   PROVIDER_TOKEN=1877036958:TEST:48af932a06745abc42b0953446ef06bb8dab579c
   ```

   **Для базы данных:**
   - По умолчанию используется SQLite
   - **Рекомендуется добавить Volume** для сохранения данных:
     - В Railway Dashboard → ваш сервис → Settings → Volumes
     - Нажмите "Add Volume"
     - Mount Path: `/data`
     - Данные будут сохраняться в `/data/bot.db`
   - Или добавьте PostgreSQL сервис для постоянного хранения

3. **Деплой**
   - Railway автоматически обнаружит Dockerfile и начнет сборку
   - После успешной сборки бот запустится автоматически

## Использование PostgreSQL (опционально)

Если вам нужны постоянные данные (история постов, платежей), добавьте PostgreSQL:

1. В Railway Dashboard добавьте PostgreSQL сервис
2. Railway автоматически создаст переменную `DATABASE_URL`
3. Зависимость `asyncpg` уже включена в `requirements.txt`

**Если данные не критичны**, можно использовать SQLite по умолчанию.

## Мониторинг

- **Логи**: Railway Dashboard → Deployments → View Logs
- **Метрики**: Railway Dashboard → Metrics
- **Переменные**: Railway Dashboard → Variables

## Обновление бота

1. Сделайте изменения в коде
2. Закоммитьте и запушьте в GitHub
3. Railway автоматически пересоберет и перезапустит бота

## Troubleshooting

### Бот не запускается
- Проверьте логи в Railway Dashboard
- Убедитесь, что все переменные окружения установлены
- Проверьте, что `BOT_TOKEN` и `CHANNEL_ID` указаны правильно

### Ошибки базы данных
- Для SQLite: убедитесь, что volume `/data` подключен и есть права на запись
- Для PostgreSQL: проверьте `DATABASE_URL` и доступность базы
- Проверьте логи: `ls -la /data` должен показывать `bot.db` файл

### Проблемы с платежами
- Проверьте `PROVIDER_TOKEN` для Smart Glocal
- Убедитесь, что бот имеет права на прием платежей

## Переменные окружения

| Переменная | Описание | Обязательная |
|------------|----------|--------------|
| `BOT_TOKEN` | Токен бота от @BotFather | ✅ Да |
| `CHANNEL_ID` | ID канала для публикации | ✅ Да |
| `MODERATORS` | ID модераторов через запятую | ✅ Да |
| `DATABASE_URL` | URL базы данных (для PostgreSQL) | ❌ Нет (по умолчанию SQLite) |
| `PROVIDER_TOKEN` | Токен Smart Glocal для оплаты картой | ❌ Нет |

## Полезные ссылки

- [Railway Documentation](https://docs.railway.app)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Smart Glocal Bot](https://t.me/SmartGlocalBot)

