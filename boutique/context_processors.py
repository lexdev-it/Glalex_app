from typing import Dict
from .models import Message

def cart_count(request) -> Dict[str, int]:
    cart = request.session.get('cart', {})
    count = 0
    if isinstance(cart, dict):
        for k, v in cart.items():
            try:
                count += int(v)
            except Exception:
                continue
    return {'cart_count': count}

def messages_badge_counts(request) -> Dict[str, int]:
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'messages_unread_total': 0}
    try:
        total = Message.objects.filter(recipient=request.user, is_read=False).count()
    except Exception:
        total = 0
    return {
        'messages_unread_total': total,
    }
