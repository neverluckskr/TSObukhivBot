from keyboards.moderator_kb import get_moderation_keyboard, get_user_info_keyboard


def test_moderation_keyboard_pagination_and_approve_all():
    kb = get_moderation_keyboard(post_id=1, user_id=2, include_approve_all=True, offset=0, total=5)
    # keyboard should contain navigation row and approve_all confirmation
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "⚠️ Подтвердить массовое одобрение" in texts
    assert "◀️" in texts or "◀️ Предыдущий" in texts
    assert "Следующий ▶️" in texts or "▶️" in texts


def test_user_info_keyboard_actions():
    kb = get_user_info_keyboard(user_id=123)
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "🚫 Забанить" in texts
    assert "✅ Разбанить" in texts
    assert "📄 Просмотреть посты" in texts
    assert "⚠️ Предупредить" in texts
    assert "↩️ Назад к модерации" in texts


def test_moderation_keyboard_owner_button():
    kb = get_moderation_keyboard(post_id=1, user_id=2, include_approve_all=False, offset=0, total=1, is_owner=True)
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "➕ Добавить модератора" in texts
