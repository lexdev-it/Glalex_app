from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.db import transaction
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from .models import Produit, Commande, DetailCommande, ProfilLivreur, ProfilAdmin, Categorie, ProfilClient, Message
from decimal import Decimal
from django.utils import timezone
import secrets
from django.contrib.auth.models import User
from django.db.utils import ProgrammingError, OperationalError
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.core.paginator import Paginator
from django import forms
from django.core.paginator import Paginator
try:
    from xhtml2pdf import pisa
except Exception:
    pisa = None
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Forms
class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = [
            'nom', 'description', 'prix', 'stock', 'categorie', 'image', 'actif'
        ]

    def clean_prix(self):
        val = self.cleaned_data.get('prix')
        if val is None:
            raise forms.ValidationError("Le prix est requis.")
        try:
            d = Decimal(val)
        except Exception:
            raise forms.ValidationError("Le prix doit être un nombre valide.")
        if d < 0:
            raise forms.ValidationError("Le prix doit être positif ou nul.")
        return d

    def clean_stock(self):
        val = self.cleaned_data.get('stock')
        if val in (None, ""):
            raise forms.ValidationError("Le stock est requis.")
        try:
            i = int(val)
        except Exception:
            raise forms.ValidationError("Le stock doit être un entier.")
        if i < 0:
            raise forms.ValidationError("Le stock doit être positif ou nul.")
        return i

    def clean_image(self):
        img = self.cleaned_data.get('image')
        if not img:
            return img
        max_size = 2 * 1024 * 1024  # 2MB
        size = getattr(img, 'size', None)
        if size and size > max_size:
            raise forms.ValidationError("L'image ne doit pas dépasser 2 Mo.")
        content_type = getattr(img, 'content_type', '') or ''
        if content_type and not content_type.startswith('image/'):
            raise forms.ValidationError("Le fichier doit être une image.")
        return img

# General views

def accueil(request):
    # Show products on landing page
    try:
        q = (request.GET.get('q') or '').strip()
        sort = (request.GET.get('sort') or 'new').strip()  # new | price_asc | price_desc
        cat = request.GET.get('cat')  # id de categorie facultatif

        produits = Produit.objects.filter(actif=True).select_related('categorie')
        # Filtre catégorie spécifique
        if cat and str(cat).isdigit():
            produits = produits.filter(categorie_id=int(cat))
        if q:
            from django.db.models import Q as _Q
            produits = produits.filter(_Q(nom__icontains=q) | _Q(description__icontains=q) | _Q(categorie__nom__icontains=q))

        # Tri par catégorie puis tri secondaire choisi
        if sort == 'price_asc':
            produits = produits.order_by('categorie__nom', 'prix', '-date_creation')
        elif sort == 'price_desc':
            produits = produits.order_by('categorie__nom', '-prix', '-date_creation')
        else:  # 'new'
            produits = produits.order_by('categorie__nom', '-date_creation')
    except Exception:
        produits = Produit.objects.filter(actif=True).order_by('-date_creation')
    cart = request.session.get('cart', {}) or {}
    cart_count = sum(cart.values()) if isinstance(cart, dict) else 0
    # Unread messages badge for logged-in users
    unread_count = 0
    if request.user.is_authenticated:
        try:
            unread_count = Message.objects.filter(recipient=request.user, is_read=False).count()
        except Exception:
            unread_count = 0
    # Unassigned orders badge for delivery users (livreurs)
    unassigned_count = 0
    if request.user.is_authenticated and hasattr(request.user, 'profillivreur'):
        try:
            unassigned_count = Commande.objects.filter(livreur__isnull=True, statut='en_attente').count()
        except Exception:
            unassigned_count = 0

    # Liste des catégories pour les filtres
    try:
        categories = Categorie.objects.all().order_by('nom')
    except Exception:
        categories = []

    return render(request, "client/index.html", {
        "produits": produits,
        "cart_count": cart_count,
        "unread_count": unread_count,
        "unassigned_count": unassigned_count,
        "categories": categories,
        "wa_number": getattr(settings, "WHATSAPP_NUMBER", ""),
        "wa_text": getattr(settings, "WHATSAPP_DEFAULT_TEXT", "Bonjour"),
    })


def login_view(request):
    next_url = request.GET.get('next') or request.POST.get('next') or reverse('accueil')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if not next_url:
                # Redirect by application role (safe if migrations missing)
                if is_app_admin(user):
                    return redirect('admin_dashboard')
                if hasattr(user, 'profillivreur') and getattr(user.profillivreur, 'actif', False):
                    return redirect('livreur_dashboard')
                return redirect('accueil')
            return redirect(next_url)
        messages.error(request, "Identifiants invalides.")
    return render(request, "auth/login.html", {"next": next_url})


def register(request):
    next_url = request.GET.get('next') or request.POST.get('next') or reverse('accueil')
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        if not username or not password1:
            messages.error(request, "Nom d'utilisateur et mot de passe requis.")
        elif password1 != password2:
            messages.error(request, "Les mots de passe ne correspondent pas.")
        else:
            from django.contrib.auth.models import User
            if User.objects.filter(username=username).exists():
                messages.error(request, "Ce nom d'utilisateur existe déjà.")
            else:
                user = User.objects.create_user(username=username, email=email, password=password1)
                # Role: par défaut 'client'. Les livreurs seront créés par l'admin via le back-office.
                login(request, user)
                return redirect(next_url)
    return render(request, "auth/register.html", {"next": next_url})


def deconnexion(request):
    logout(request)
    return redirect('accueil')


# Client views

def client_boutique(request):
    produits = Produit.objects.filter(actif=True).order_by('-date_creation')
    cart = request.session.get('cart', {}) or {}
    cart_count = sum(cart.values()) if isinstance(cart, dict) else 0
    return render(request, "client/index.html", {
        "produits": produits,
        "cart_count": cart_count,
        "wa_number": getattr(settings, "WHATSAPP_NUMBER", ""),
        "wa_text": getattr(settings, "WHATSAPP_DEFAULT_TEXT", "Bonjour"),
    })


def client_commandes(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('connexion')}?next={reverse('client_commandes')}")
    commandes = Commande.objects.filter(client=request.user).order_by('-date_commande')
    return render(request, "client/commandes.html", {"commandes": commandes})


# Panier (session)

def _get_cart(request):
    cart = request.session.get('cart')
    if not isinstance(cart, dict):
        cart = {}
        request.session['cart'] = cart
        request.session.modified = True
    return cart

def add_to_cart(request, produit_id: int):
    produit = get_object_or_404(Produit, pk=produit_id, actif=True)
    # Restrict: only clients can add to cart.
    # Admin/staff/superuser and delivery-role users cannot add to cart.
    is_admin_like = request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser)
    # Detect a livreur role without tightly coupling to model names/groups
    has_livreur_attr = (getattr(request.user, 'livreur', None) is not None) or (getattr(request.user, 'profillivreur', None) is not None)
    in_livreur_group = False
    try:
        in_livreur_group = request.user.is_authenticated and request.user.groups.filter(name__iexact='livreur').exists()
    except Exception:
        in_livreur_group = False
    if is_admin_like or has_livreur_attr or in_livreur_group:
        messages.warning(request, "Seuls les clients peuvent ajouter des articles au panier.")
        return redirect('client_boutique')
    cart = _get_cart(request)
    pid = str(produit.id)
    # lire quantité depuis POST ou GET, défaut 1
    try:
        qty_raw = request.POST.get('qty') or request.GET.get('qty') or '1'
        qty = int(qty_raw)
        if qty < 1:
            qty = 1
        if qty > 100:
            qty = 100
    except (TypeError, ValueError):
        qty = 1
    cart[pid] = cart.get(pid, 0) + qty
    request.session['cart'] = cart  # réassigner explicitement pour persister
    request.session.modified = True
    messages.success(request, f"{qty} × {produit.nom} ajouté(s) au panier.")
    # rester sur la boutique pour continuer les achats
    return redirect('client_boutique')


def view_cart(request):
    cart = _get_cart(request)
    items = []
    total = Decimal('0.00')
    for pid, qty in cart.items():
        produit = get_object_or_404(Produit, pk=int(pid))
        sous_total = Decimal(qty) * produit.prix
        total += sous_total
        items.append({
            'produit': produit,
            'quantite': qty,
            'sous_total': sous_total,
        })
    cart_count = sum(cart.values()) if isinstance(cart, dict) else 0
    return render(request, "client/panier.html", {"items": items, "total": total, "cart_count": cart_count})


def cart_update(request, produit_id: int):
    """Mettre à jour la quantité d'un produit dans le panier (session). Si qty <= 0, on supprime l'article."""
    cart = _get_cart(request)
    pid = str(produit_id)
    if request.method == 'POST':
        try:
            qty = int(request.POST.get('qty', '1'))
        except (TypeError, ValueError):
            qty = 1
        if qty <= 0:
            if pid in cart:
                cart.pop(pid, None)
                messages.info(request, "Article retiré du panier.")
        else:
            if qty > 100:
                qty = 100
            cart[pid] = qty
            messages.success(request, "Quantité mise à jour.")
        request.session['cart'] = cart
        request.session.modified = True
    return redirect('view_cart')


def cart_remove(request, produit_id: int):
    """Retirer un produit du panier (session)."""
    cart = _get_cart(request)
    pid = str(produit_id)
    if pid in cart:
        cart.pop(pid)
        request.session['cart'] = cart
        request.session.modified = True
        messages.info(request, "Article retiré du panier.")
    return redirect('view_cart')


@login_required
def checkout(request):
    # Only client users can checkout (no staff/superuser/livreur)
    is_admin_like = request.user.is_staff or request.user.is_superuser
    has_livreur_attr = (getattr(request.user, 'livreur', None) is not None) or (getattr(request.user, 'profillivreur', None) is not None)
    in_livreur_group = False
    try:
        in_livreur_group = request.user.groups.filter(name__iexact='livreur').exists()
    except Exception:
        in_livreur_group = False
    if is_admin_like or has_livreur_attr or in_livreur_group:
        messages.warning(request, "Seuls les clients peuvent passer commande.")
        return redirect('client_boutique')
    cart = _get_cart(request)
    if not cart:
        messages.info(request, "Votre panier est vide.")
        return redirect('client_boutique')

    # Simple order creation (adresse à compléter via formulaire ultérieur)
    now = timezone.now().strftime('%Y%m%d%H%M%S')
    numero = f"CMD{now}{request.user.id}"

    total = Decimal('0.00')
    for pid, qty in cart.items():
        produit = get_object_or_404(Produit, pk=int(pid))
        total += Decimal(qty) * produit.prix

    commande = Commande.objects.create(
        client=request.user,
        numero_commande=numero,
        statut='en_attente',
        total=total,
        adresse_livraison='(à renseigner)',
    )

    for pid, qty in cart.items():
        produit = get_object_or_404(Produit, pk=int(pid))
        DetailCommande.objects.create(
            commande=commande,
            produit=produit,
            quantite=qty,
            prix_unitaire=produit.prix,
        )

    # Vider le panier
    request.session['cart'] = {}
    request.session.modified = True
    messages.success(request, f"Commande {commande.numero_commande} créée.")
    return redirect('client_commandes')


# New views for client checkout flow

def _get_cart(request):
    cart = request.session.get('cart', {})
    if not isinstance(cart, dict):
        cart = {}
    return cart

def _cart_items_and_total(cart):
    ids = [int(pid) for pid in cart.keys() if str(pid).isdigit()]
    produits = Produit.objects.filter(id__in=ids)
    items = []
    total = Decimal('0.00')
    for p in produits:
        qty = int(cart.get(str(p.id), 0))
        if qty <= 0:
            continue
        sous_total = p.prix * qty
        total += sous_total
        items.append({
            'produit': p,
            'quantite': qty,
            'sous_total': sous_total,
        })
    return items, total

@login_required
def client_checkout(request):
    cart = _get_cart(request)
    items, total = _cart_items_and_total(cart)
    if request.method == 'GET':
        if not items:
            messages.info(request, "Votre panier est vide.")
            return redirect('/')
        return render(request, 'client/checkout.html', {
            'items': items,
            'total': total,
        })

    # POST: créer la commande
    if not items:
        messages.error(request, "Panier vide.")
        return redirect('/')

    nom_complet = request.POST.get('nom_complet', '').strip()
    telephone = request.POST.get('telephone', '').strip()
    ville = request.POST.get('ville', '').strip()
    adresse_livraison = request.POST.get('adresse_livraison', '').strip()
    payment_method = request.POST.get('payment_method')  # 'tmoney' ou 'flooz'

    if not (nom_complet and telephone and adresse_livraison and payment_method):
        messages.error(request, "Merci de renseigner tous les champs obligatoires.")
        return render(request, 'client/checkout.html', {
            'items': items,
            'total': total,
            'form': {
                'nom_complet': nom_complet,
                'telephone': telephone,
                'ville': ville,
                'adresse_livraison': adresse_livraison,
                'payment_method': payment_method,
            }
        })

    # Générer un numéro de commande simple
    ts = timezone.now().strftime('%Y%m%d%H%M%S')
    numero = f"GLA{ts}{request.user.id}"

    commande = Commande.objects.create(
        client=request.user,
        numero_commande=numero,
        date_commande=timezone.now(),
        statut='en_attente',
        total=total,
        adresse_livraison=adresse_livraison,
        nom_complet=nom_complet,
        telephone=telephone,
        ville=ville,
        payment_method=payment_method,
        payment_status='pending',
    )

    # Détails
    for it in items:
        p = it['produit']
        q = it['quantite']
        DetailCommande.objects.create(
            commande=commande,
            produit=p,
            quantite=q,
            prix_unitaire=p.prix,
        )

    # Vider le panier
    request.session['cart'] = {}
    request.session.modified = True

    try:
        if request.user.email:
            subject = f"Glalex - Commande {commande.numero_commande}"
            body = render_to_string('emails/confirmation_commande.txt', {
                'commande': commande,
                'user': request.user,
                'request_scheme': request.scheme,
                'request_host': request.get_host(),
            })
            email = EmailMessage(subject, body, to=[request.user.email])
            email.send(fail_silently=True)
    except Exception:
        pass

    messages.success(request, "Commande créée. Procédez au paiement.")
    return redirect('client_paiement', numero=commande.numero_commande)

@login_required
def client_paiement(request, numero):
    """Page informative: paiement à la livraison. Le livreur confirmera."""
    commande = get_object_or_404(Commande, numero_commande=numero, client=request.user)
    return render(request, 'client/paiement.html', {
        'commande': commande,
    })

@login_required
def client_facture(request, numero):
    # Fetch by numero only; authorize client, admin, or assigned livreur
    commande = get_object_or_404(
        Commande.objects.select_related('client').select_related('livreur__user').prefetch_related('details__produit'),
        numero_commande=numero,
    )
    is_owner = (commande.client_id == getattr(request.user, 'id', None))
    is_admin = False
    try:
        is_admin = is_app_admin(request.user)
    except Exception:
        is_admin = False
    is_assigned_livreur = False
    try:
        is_assigned_livreur = hasattr(request.user, 'profillivreur') and commande.livreur and (commande.livreur.user_id == request.user.id)
    except Exception:
        is_assigned_livreur = False
    if not (is_owner or is_admin or is_assigned_livreur):
        messages.error(request, "Accès refusé à cette facture.")
        return redirect('accueil')
    return render(request, 'client/facture.html', {
        'commande': commande,
    })

@login_required
def client_facture_pdf(request, numero):
    if pisa is None:
        messages.error(request, "Génération PDF indisponible: xhtml2pdf non installé.")
        return redirect('client_facture', numero=numero)
    # Fetch by numero only; authorize client, admin, or assigned livreur
    commande = get_object_or_404(
        Commande.objects.select_related('client').select_related('livreur__user').prefetch_related('details__produit'),
        numero_commande=numero,
    )
    is_owner = (commande.client_id == getattr(request.user, 'id', None))
    is_admin = False
    try:
        is_admin = is_app_admin(request.user)
    except Exception:
        is_admin = False
    is_assigned_livreur = False
    try:
        is_assigned_livreur = hasattr(request.user, 'profillivreur') and commande.livreur and (commande.livreur.user_id == request.user.id)
    except Exception:
        is_assigned_livreur = False
    if not (is_owner or is_admin or is_assigned_livreur):
        messages.error(request, "Accès refusé à cette facture.")
        return redirect('accueil')
    # Autoriser le PDF uniquement si le paiement a été confirmé par le livreur
    if commande.payment_status != 'paid':
        messages.info(request, "Le paiement n'est pas encore confirmé. Le PDF sera disponible après confirmation par le livreur.")
        return redirect('client_facture', numero=numero)
    html = render_to_string('client/facture.html', {'commande': commande})
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="facture_{commande.numero_commande}.pdf"'
    pisa.CreatePDF(src=html, dest=response)
    return response

@login_required
def client_messages(request):
    """
    Centre messages côté client:
    - Suggestions/Admin/Factures: lecture seule (comme avant)
    - Nouveau: Discussion avec le(s) livreur(s) assigné(s) (bi-directionnel)
    """
    if not request.user.is_authenticated:
        return redirect(f"{reverse('connexion')}?next={reverse('client_messages')}")

    # Déterminer l'onglet actif via query ?tab= (sugg | fact | livr)
    active_tab = request.GET.get('tab') or ''
    if active_tab not in ('sugg', 'fact', 'livr'):
        active_tab = 'sugg'

    # Séparer le fil Admin/Suggestions des échanges livreur
    admins = get_user_model().objects.filter(Q(is_staff=True) | Q(is_superuser=True))
    admin_thread = Message.objects.filter(
        (Q(sender__in=admins, recipient=request.user) | Q(sender=request.user, recipient__in=admins))
    ).select_related('sender', 'recipient').order_by('created_at')

    # Annotate messages with a potential facture_url extracted from the body
    try:
        import re
        facture_pat = re.compile(r"(/facture/[\w-]+/?)", re.IGNORECASE)
        absolute_pat = re.compile(r"https?://\S+", re.IGNORECASE)
        for _m in admin_thread:
            _m.facture_url = None
            body = _m.body or ""
            m1 = facture_pat.search(body)
            if m1:
                url = m1.group(1)
                if not url.endswith('/'):
                    url += '/'
                _m.facture_url = url
                # remove this url from display body
                body_no_facture = facture_pat.sub('', body)
            else:
                m2 = absolute_pat.search(body)
                if m2:
                    _m.facture_url = m2.group(0)
                body_no_facture = body
            # compact whitespace for display
            _m.body_display = re.sub(r"\n{3,}", "\n\n", body_no_facture).strip()
    except Exception:
        pass

    # --- Nouveau: discussions client ↔ livreur ---
    # Restreindre aux livreurs ayant effectivement un échange (message client<->livreur)
    from .models import Commande
    livreur_msg_user_ids = Message.objects.filter(
        (Q(sender__groups__name='') | Q(recipient__groups__name=''))  # placeholder to keep Q structure
    )
    # Récupérer tous les users ayant échangé avec client ET qui sont des livreurs par leur profil
    try:
        # IDs users livreurs qui ont un thread avec ce client
        msg_user_ids = Message.objects.filter(
            Q(sender__id=request.user.id) | Q(recipient__id=request.user.id)
        ).values_list('sender_id', 'recipient_id')
        ids = set()
        for s_id, r_id in msg_user_ids:
            if s_id and s_id != request.user.id:
                ids.add(s_id)
            if r_id and r_id != request.user.id:
                ids.add(r_id)
        # Restreindre à ceux qui ont un profil livreur
        livreurs = list(get_user_model().objects.filter(id__in=list(ids), profillivreur__isnull=False).order_by('username'))
    except Exception:
        livreurs = []

    selected_livreur = None
    livreur_thread = []
    selected_livreur_id = request.GET.get('livreur') or request.POST.get('livreur_id')

    # POST: envoi d'un message au livreur sélectionné
    if request.method == 'POST':
        body = (request.POST.get('body') or '').strip()
        if selected_livreur_id and body:
            try:
                from django.contrib.auth.models import User as DjangoUser2
                selected_livreur = DjangoUser2.objects.get(pk=int(selected_livreur_id))
                # Vérifier que ce livreur est bien lié à une commande de ce client
                if Commande.objects.filter(client=request.user, livreur__user=selected_livreur).exists():
                    Message.objects.create(sender=request.user, recipient=selected_livreur, body=body)
                    messages.success(request, "Message envoyé au livreur.")
                    return redirect(f"{reverse('client_messages')}?tab=livr&livreur={selected_livreur.id}#pane-livr")
                else:
                    messages.error(request, "Livreur non autorisé.")
            except Exception as e:
                messages.error(request, f"Erreur d'envoi: {e}")
        elif selected_livreur_id and not body:
            messages.error(request, "Votre message est vide.")

    # Charger le fil avec le livreur sélectionné
    if selected_livreur_id and selected_livreur is None:
        try:
            from django.contrib.auth.models import User as DjangoUser2
            selected_livreur = DjangoUser2.objects.get(pk=int(selected_livreur_id))
        except Exception:
            selected_livreur = None
    if selected_livreur and Commande.objects.filter(client=request.user, livreur__user=selected_livreur).exists():
        # Marquer comme lus les messages entrants de ce livreur vers le client
        Message.objects.filter(recipient=request.user, sender=selected_livreur, is_read=False).update(is_read=True)
        livreur_thread = Message.objects.filter(
            Q(sender=request.user, recipient=selected_livreur) | Q(sender=selected_livreur, recipient=request.user)
        ).select_related('sender', 'recipient').order_by('created_at')

    # Compteurs non-lus par onglet
    admin_unread = Message.objects.filter(recipient=request.user, sender__in=admins, is_read=False).count()
    # Unread côté livreurs: uniquement par expéditeurs qui sont des livreurs
    from django.contrib.auth.models import User as DjangoUser
    livreur_users_qs = DjangoUser.objects.filter(profillivreur__isnull=False)
    livreur_unread = Message.objects.filter(recipient=request.user, sender__in=livreur_users_qs, is_read=False).count()

    # Marquer admin comme lus seulement si onglet sugg/fact explicitement actif
    if active_tab in ('sugg', 'fact'):
        Message.objects.filter(recipient=request.user, sender__in=admins, is_read=False).update(is_read=True)

    cart = request.session.get('cart', {}) or {}
    cart_count = sum(cart.values()) if isinstance(cart, dict) else 0
    client_unread_total = (admin_unread or 0) + (livreur_unread or 0)
    return render(request, 'client/messages.html', {
        'thread': admin_thread,
        'cart_count': cart_count,
        'livreurs': livreurs,
        'selected_livreur': selected_livreur,
        'livreur_thread': livreur_thread,
        'active_tab': active_tab,
        'admin_unread': admin_unread,
        'livreur_unread': livreur_unread,
        'client_unread_total': client_unread_total,
    })


@login_required
def client_suggestions(request):
    """
    Page où le client envoie une suggestion (one-way) à l'admin. Pas de réponse ici.
    """
    admin_users = get_user_model().objects.filter(Q(is_staff=True) | Q(is_superuser=True)).distinct().order_by('-is_superuser', '-is_staff')
    if not admin_users:
        messages.error(request, "Aucun administrateur disponible pour recevoir votre suggestion.")
        logger.warning("client_suggestions: aucun admin/staff trouvé; user=%s", request.user.id)
        return redirect('client_messages')

    if request.method == 'POST':
        body = (request.POST.get('body') or '').strip()
        if body:
            # Envoyer à tous les admins/staff
            created_ids = []
            for admin_user in admin_users:
                m = Message.objects.create(sender=request.user, recipient=admin_user, body=body)
                created_ids.append(m.id)
            logger.info("client_suggestions: suggestion envoyee; sender=%s recipients=%s message_ids=%s", request.user.id, [u.id for u in admin_users], created_ids)
            # Notification e-mail si configurée
            try:
                from django.core.mail import mail_admins, send_mail
                subj = "Nouvelle suggestion client"
                content = f"Client: {request.user.username}\n\n{body}"
                try:
                    mail_admins(subject=subj, message=content, fail_silently=True)
                except Exception:
                    # fallback: envoyer aux emails des admins connus
                    for admin_user in admin_users:
                        if getattr(admin_user, 'email', None):
                            try:
                                send_mail(subj, content, None, [admin_user.email], fail_silently=True)
                            except Exception:
                                pass
            except Exception:
                logger.exception("client_suggestions: erreur pendant l'envoi email admins")
            messages.success(request, "Suggestion envoyée à l'administrateur.")
            return redirect('client_messages')
        messages.error(request, "La suggestion ne peut pas être vide.")

    cart = request.session.get('cart', {}) or {}
    cart_count = sum(cart.values()) if isinstance(cart, dict) else 0
    return render(request, 'client/suggestions.html', {
        'cart_count': cart_count,
    })


@login_required
def admin_inbox(request):
    """
    Boîte de réception admin: Boîte à suggestions (clients) + section livreurs.
    """
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur.")
        return redirect('accueil')
    # Récupérer les utilisateurs qui ont envoyé des messages à l'admin
    senders_qs = Message.objects.filter(recipient=request.user).values_list('sender_id', flat=True).distinct()
    
    # Récupérer les clients qui ont envoyé des messages (suggestions)
    suggesters = list(get_user_model().objects.filter(
        id__in=senders_qs,
        profillivreur__isnull=True  # Exclure les livreurs
    ).order_by('username'))
    
    # Récupérer les livreurs qui ont envoyé des messages
    livreurs_avec_messages = list(get_user_model().objects.filter(
        id__in=senders_qs,
        profillivreur__isnull=False  # Uniquement les livreurs
    ).order_by('username'))
    
    # Récupérer tous les livreurs pour l'affichage, même sans messages
    livreurs = list(get_user_model().objects.filter(
        profillivreur__isnull=False
    ).order_by('username'))
    
    # Fusionner les listes pour avoir les livreurs avec messages en premier
    # et marquer ceux qui ont des messages non lus
    for u in suggesters + livreurs_avec_messages + livreurs:
        u.unread_count = Message.objects.filter(
            sender=u, 
            recipient=request.user, 
            is_read=False
        ).count()
    
    # Créer une liste de tous les livreurs uniques avec leurs messages non lus
    livreurs_uniques = {}
    for livreur in livreurs_avec_messages + [l for l in livreurs if l not in livreurs_avec_messages]:
        if livreur.id not in livreurs_uniques:
            livreurs_uniques[livreur.id] = livreur
    
    # Total non-lus pour badge navbar
    admin_unread_total = Message.objects.filter(
        recipient=request.user, 
        is_read=False
    ).count()

    return render(request, 'boutique_admin/messages_index.html', {
        'suggesters': suggesters,
        'livreurs': list(livreurs_uniques.values()),
        'admin_unread_total': admin_unread_total,
        'messages_list': Message.objects.filter(
            recipient=request.user
        ).select_related('sender', 'recipient').order_by('-created_at'),
    })


@login_required
def admin_messages(request, client_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé.")
        return redirect('accueil')
    client = get_object_or_404(get_user_model(), id=client_id)
    # Marquer comme lus les messages entrants non lus
    Message.objects.filter(recipient=request.user, sender=client, is_read=False).update(is_read=True)

    if request.method == 'POST':
        body = (request.POST.get('body') or '').strip()
        if body:
            Message.objects.create(sender=request.user, recipient=client, body=body)
            messages.success(request, "Message envoyé.")
            return redirect('admin_messages', client_id=client.id)
        else:
            messages.error(request, "Le message ne peut pas être vide.")

    thread = Message.objects.filter(
        (Q(sender=request.user, recipient=client) | Q(sender=client, recipient=request.user))
    ).select_related('sender', 'recipient').order_by('created_at')
    return render(request, 'boutique_admin/messages.html', {
        'client': client,
        'thread': thread,
    })


@login_required
def admin_livreur_messages(request, livreur_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé.")
        return redirect('accueil')
    livreur = get_object_or_404(get_user_model(), id=livreur_id)
    # Marquer comme lus les messages entrants non lus (du livreur vers l'admin)
    Message.objects.filter(recipient=request.user, sender=livreur, is_read=False).update(is_read=True)

    if request.method == 'POST':
        body = (request.POST.get('body') or '').strip()
        if body:
            m = Message.objects.create(sender=request.user, recipient=livreur, body=body)
            try:
                logger.info("admin_livreur_messages: admin=%s -> livreur=%s msg_id=%s", request.user.id, livreur.id, m.id)
            except Exception:
                pass
            messages.success(request, "Message envoyé au livreur.")
            return redirect('admin_livreur_messages', livreur_id=livreur_id)  # Redirection vers la conversation
        else:
            messages.error(request, "Le message ne peut pas être vide.")

    thread = Message.objects.filter(
        (Q(sender=request.user, recipient=livreur) | Q(sender=livreur, recipient=request.user))
    ).select_related('sender', 'recipient').order_by('created_at')
    return render(request, 'boutique_admin/messages_livreur.html', {
        'livreur': livreur,
        'thread': thread,
    })


@login_required
def livreur_messages(request):
    """
    Messages destinés au livreur depuis l'admin,
    et espace de discussion avec les clients affectés au livreur.
    """
    # Doit être un livreur
    if getattr(request.user, 'profillivreur', None) is None:
        messages.error(request, "Accès réservé aux livreurs.")
        return redirect('accueil')

    # Prendre tous les comptes admin/staff comme correspondants possibles
    admins = get_user_model().objects.filter(Q(is_staff=True) | Q(is_superuser=True))
    
    # Marquer comme lus tous les messages entrants des admins vers ce livreur
    Message.objects.filter(recipient=request.user, sender__in=admins, is_read=False).update(is_read=True)
    
    # Construire le fil avec n'importe quel admin (agrégé)
    admin_thread = Message.objects.filter(
        Q(sender__in=admins, recipient=request.user) | Q(sender=request.user, recipient__in=admins)
    ).select_related('sender', 'recipient').order_by('created_at')

    # Construire la liste des clients liés aux commandes assignées à ce livreur
    try:
        livreur_prof = request.user.profillivreur
        client_ids = (
            Commande.objects.filter(livreur=livreur_prof)
            .values_list('client_id', flat=True).distinct()
        )
        clients = list(get_user_model().objects.filter(id__in=client_ids).order_by('username'))
    except Exception:
        clients = []

    # Defaults to avoid UnboundLocalError on various code paths
    is_admin_message = False
    admin_thread = []
    clients = []
    selected_client = None
    client_thread = []

    # Gestion sélection client (GET) et envoi message (POST)
    selected_client_id = request.GET.get('client') or request.POST.get('client_id')

    # POST: envoi d'un message
    if request.method == 'POST':
        body = (request.POST.get('body') or '').strip()
        is_admin_message = request.POST.get('admin_message') == '1'
        
        if not body:
            messages.error(request, "Le message ne peut pas être vide.")
        else:
            try:
                if is_admin_message:
                    # Envoyer un message à l'admin
                    admin = admins.first()  # Prend le premier admin disponible
                    if admin:
                        Message.objects.create(
                            sender=request.user,
                            recipient=admin,
                            body=body
                        )
                        messages.success(request, "Message envoyé à l'administration.")
                        return redirect(f"{reverse('livreur_messages')}?tab=admin")
                else:
                    # Envoyer un message à un client
                    if selected_client_id:
                        selected_client = get_user_model().objects.get(pk=int(selected_client_id))
                        if Commande.objects.filter(livreur=livreur_prof, client=selected_client).exists():
                            Message.objects.create(
                                sender=request.user,
                                recipient=selected_client,
                                body=body
                            )
                            messages.success(request, "Message envoyé au client.")
                            return redirect(f"{reverse('livreur_messages')}?tab=clients&client={selected_client.id}")
                        else:
                            messages.error(request, "Client non autorisé.")
            except Exception as e:
                messages.error(request, f"Erreur lors de l'envoi du message: {e}")

    # Afficher le fil avec le client sélectionné (GET ou après POST)
    if selected_client_id and not is_admin_message:
        try:
            selected_client = get_user_model().objects.get(pk=int(selected_client_id))
            # Marquer comme lus les messages entrants de ce client
            Message.objects.filter(recipient=request.user, sender=selected_client, is_read=False).update(is_read=True)
            client_thread = Message.objects.filter(
                Q(sender=request.user, recipient=selected_client) | 
                Q(sender=selected_client, recipient=request.user)
            ).select_related('sender', 'recipient').order_by('created_at')
        except Exception:
            selected_client = None

    # Déterminer l'onglet actif
    active_tab = 'clients' if (request.GET.get('tab') == 'clients' or (selected_client and not is_admin_message)) else 'admin'

    return render(request, 'livreur/messages.html', {
        'thread': admin_thread,
        'clients': clients,
        'selected_client': selected_client,
        'client_thread': client_thread,
        'active_tab': active_tab,
    })

# Admin views (use unique namespace to avoid conflict with Django admin templates)

@login_required
def admin_dashboard(request):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    # KPIs
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Defaults to avoid UnboundLocalError
    clients_count = 0
    chiffre_affaires = 0
    commandes_count = 0
    produits_actifs = 0
    recent_cmds = []

    try:
        # Clients = utilisateurs ayant un profil OU ayant passé au moins une commande
        clients_count = (
            User.objects.filter(
                Q(profilclient__isnull=False) | Q(commande__isnull=False),
                is_staff=False,
                is_superuser=False,
            )
            .distinct()
            .count()
        )
    except Exception:
        pass
    try:
        commandes_month_qs = Commande.objects.filter(
            payment_status='paid',
            date_commande__date__gte=month_start.date(),
            date_commande__date__lte=now.date(),
        )
        chiffre_affaires = (
            commandes_month_qs.aggregate(total=Sum('total'))['total'] or 0
        )
        commandes_count = commandes_month_qs.count()
    except Exception:
        pass
    try:
        produits_actifs = Produit.objects.filter(actif=True).count()
    except Exception:
        pass
    try:
        recent_cmds = (
            Commande.objects.select_related('client')
            .order_by('-date_commande')[:5]
        )
    except Exception:
        pass

    # Dernière connexion de l'admin
    last_login = getattr(request.user, 'last_login', None)

    # Unified tasks: stocks, messages, commandes
    low_threshold = 5
    try:
        zero_count = Produit.objects.filter(stock__lte=0).count()
        low_count = Produit.objects.filter(stock__gt=0, stock__lte=low_threshold, actif=True).count()
    except Exception:
        zero_count = 0
        low_count = 0

    # Unread messages by sender type
    try:
        unread_total = Message.objects.filter(recipient=request.user, is_read=False)
        livreur_user_ids = ProfilLivreur.objects.values_list('user_id', flat=True)
        unread_from_livreurs = unread_total.filter(sender_id__in=livreur_user_ids).count()
        unread_from_clients = unread_total.exclude(sender_id__in=livreur_user_ids).count()
        admin_unread_total = unread_total.count()
    except Exception:
        unread_from_livreurs = 0
        unread_from_clients = 0
        admin_unread_total = 0

    # New orders today
    try:
        new_orders_today = Commande.objects.filter(date_commande__date=now.date()).count()
    except Exception:
        new_orders_today = 0

    return render(request, "boutique_admin/index.html", {
        'clients_count': clients_count,
        'chiffre_affaires': chiffre_affaires,
        'commandes_count': commandes_count,
        'produits_actifs': produits_actifs,
        'recent_cmds': recent_cmds,
        'last_login': last_login,
        'now': now,
        # tasks context
        'low_threshold': low_threshold,
        'dash_zero_count': zero_count,
        'dash_low_count': low_count,
        'dash_unread_clients': unread_from_clients,
        'dash_unread_livreurs': unread_from_livreurs,
        'dash_unread_total': admin_unread_total,
        'dash_new_orders_today': new_orders_today,
    })


@login_required
def admin_livreurs_list(request):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    q = request.GET.get('q', '').strip()
    livreurs = ProfilLivreur.objects.all().select_related('user')
    if q:
        livreurs = livreurs.filter(user__username__icontains=q)
    return render(request, "boutique_admin/livreurs_list.html", {"livreurs": livreurs, "q": q})


@login_required
def admin_livreur_add(request):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        vehicule = request.POST.get('vehicule', '').strip()
        numero_permis = request.POST.get('numero_permis', '').strip()
        zone_livraison = request.POST.get('zone_livraison', '').strip()
        actif = request.POST.get('actif') == 'on'
        photo = request.FILES.get('photo')
        date_naissance = request.POST.get('date_naissance') or None
        numero_cni = request.POST.get('numero_cni', '').strip() or None
        quartier = request.POST.get('quartier', '').strip()

        if not username or not password:
            messages.error(request, "Nom d'utilisateur et mot de passe sont requis.")
        elif get_user_model().objects.filter(username=username).exists():
            messages.error(request, "Ce nom d'utilisateur existe déjà.")
        else:
            user = get_user_model().objects.create_user(username=username, password=password)
            ProfilLivreur.objects.create(
                user=user,
                telephone=telephone or '',
                vehicule=vehicule or '',
                numero_permis=numero_permis or '',
                zone_livraison=zone_livraison or '',
                actif=actif,
                photo=photo,
                date_naissance=date_naissance,
                numero_cni=numero_cni,
                quartier=quartier or '',
            )
            messages.success(request, f"Livreur '{username}' créé avec succès.")
            return redirect('admin_livreurs_list')

    return render(request, "boutique_admin/livreur_add.html")


@login_required
def admin_livreur_edit(request, livreur_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    profil = get_object_or_404(ProfilLivreur.objects.select_related('user'), pk=livreur_id)
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        vehicule = request.POST.get('vehicule', '').strip()
        numero_permis = request.POST.get('numero_permis', '').strip()
        zone_livraison = request.POST.get('zone_livraison', '').strip()
        actif = request.POST.get('actif') == 'on'
        new_password = request.POST.get('password', '').strip()
        new_photo = request.FILES.get('photo')
        date_naissance = request.POST.get('date_naissance') or None
        numero_cni = request.POST.get('numero_cni', '').strip() or None
        quartier = request.POST.get('quartier', '').strip()
        try:
            with transaction.atomic():
                if username and username != profil.user.username:
                    profil.user.username = username
                if new_password:
                    profil.user.set_password(new_password)
                profil.user.is_active = actif
                profil.user.save()

                profil.telephone = telephone
                profil.vehicule = vehicule
                profil.numero_permis = numero_permis
                profil.zone_livraison = zone_livraison
                profil.actif = actif
                if new_photo:
                    profil.photo = new_photo
                profil.date_naissance = date_naissance
                profil.numero_cni = numero_cni
                profil.quartier = quartier
                profil.save()
            messages.success(request, "Livreur modifié avec succès.")
            return redirect('admin_livreurs_list')
        except Exception as e:
            messages.error(request, f"Erreur lors de la modification: {e}")
    return render(request, 'boutique_admin/livreur_form.html', { 'mode': 'edit', 'livreur': profil })


@login_required
def admin_livreur_delete(request, livreur_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    profil = get_object_or_404(ProfilLivreur.objects.select_related('user'), pk=livreur_id)
    if request.method == 'POST':
        try:
            # Soft-delete: désactiver au lieu de supprimer pour éviter soucis de FK
            profil.actif = False
            profil.save()
            profil.user.is_active = False
            profil.user.save()
            messages.success(request, "Livreur désactivé.")
        except Exception as e:
            messages.error(request, f"Erreur: {e}")
        return redirect('admin_livreurs_list')
    messages.info(request, f"Confirmer la désactivation du livreur: {profil.user.username}")
    return redirect('admin_livreurs_list')


@login_required
def admin_livreur_reset_password(request, livreur_id: int):
    if request.method != 'POST':
        return redirect('admin_livreur_edit', livreur_id=livreur_id)
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    profil = get_object_or_404(ProfilLivreur.objects.select_related('user'), pk=livreur_id)
    temp_pwd = secrets.token_urlsafe(8)
    profil.user.set_password(temp_pwd)
    profil.user.save(update_fields=['password'])
    messages.success(request, f"Mot de passe du livreur réinitialisé. Nouveau mot de passe temporaire: {temp_pwd}")
    try:
        if profil.user.email:
            subject = "Réinitialisation mot de passe Livreur"
            body = (
                f"Bonjour {profil.user.username},\n\n"
                f"Votre mot de passe a été réinitialisé par l'administrateur.\n"
                f"Nouveau mot de passe temporaire: {temp_pwd}\n\n"
                f"Merci de vous connecter et de le changer immédiatement."
            )
            EmailMessage(subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [profil.user.email]).send(fail_silently=True)
    except Exception:
        pass
    return redirect('admin_livreur_edit', livreur_id=livreur_id)


@login_required
def admin_livreur_set_password(request, livreur_id: int):
    if request.method != 'POST':
        return redirect('admin_livreurs_list')
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    profil = get_object_or_404(ProfilLivreur.objects.select_related('user'), pk=livreur_id)
    new_pwd = (request.POST.get('new_password') or '').strip()
    if not new_pwd:
        messages.error(request, "Le nouveau mot de passe est requis.")
        return redirect('admin_livreurs_list')
    try:
        profil.user.set_password(new_pwd)
        profil.user.save(update_fields=['password'])
        messages.success(request, f"Mot de passe mis à jour pour {profil.user.username}.")
    except Exception as e:
        messages.error(request, f"Erreur lors de la mise à jour du mot de passe: {e}")
    return redirect('admin_livreurs_list')


@login_required
def admin_produits_list(request):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    q = request.GET.get('q', '').strip()
    cat = request.GET.get('cat')
    actif = request.GET.get('actif')  # '1' | '0' | None

    produits_qs = (
        Produit.objects.all()
        .select_related('categorie')
        .order_by('-date_creation')
    )
    if q:
        produits_qs = produits_qs.filter(nom__icontains=q)
    if cat and str(cat).isdigit():
        produits_qs = produits_qs.filter(categorie_id=int(cat))
    if actif in {'1','0'}:
        produits_qs = produits_qs.filter(actif=(actif == '1'))

    # Pagination avec per_page
    page_number = request.GET.get('page')
    raw_per_page = request.GET.get('per_page')
    allowed_pp = [10, 20, 50]
    try:
        per_page = int(raw_per_page) if raw_per_page is not None else 10
    except ValueError:
        per_page = 10
    if per_page not in allowed_pp:
        per_page = 10
    paginator = Paginator(produits_qs, per_page)
    page_obj = paginator.get_page(page_number)

    categories = Categorie.objects.all().order_by('nom')

    return render(request, 'boutique_admin/produits_list.html', {
        'produits': page_obj.object_list,
        'page_obj': page_obj,
        'q': q,
        'categories': categories,
        'cat': int(cat) if cat and str(cat).isdigit() else '',
        'actif': actif or '',
        'per_page': per_page,
        'allowed_pp': allowed_pp,
    })


@login_required
def admin_produit_add(request):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    categories = Categorie.objects.all().order_by('nom')
    if request.method == 'POST':
        form = ProduitForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Produit créé avec succès.")
            return redirect('admin_produits_list')
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = ProduitForm()
    return render(request, 'boutique_admin/produit_form.html', { 'categories': categories, 'mode': 'add', 'form': form, 'produit': None })


@login_required
def admin_produit_edit(request, produit_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    
    # Récupération du produit et des catégories
    produit = get_object_or_404(Produit, pk=produit_id)
    categories = Categorie.objects.all().order_by('nom')

    if request.method == 'POST':
        clear_image = request.POST.get('clear_image') == 'on'
        form = ProduitForm(request.POST, request.FILES, instance=produit)
        if form.is_valid():
            saved = form.save(commit=False)
            if clear_image and saved.image:
                saved.image.delete(save=False)
                saved.image = None
            saved.save()
            messages.success(request, "Le produit a été mis à jour avec succès.")
            return redirect('admin_produits_list')
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = ProduitForm(instance=produit)

    context = {
        'produit': produit,
        'categories': categories,
        'mode': 'edit',
        'form': form,
    }

    return render(request, "boutique_admin/produit_form.html", context)


@login_required
def admin_produit_delete(request, produit_id: int):
    # ... (pas de changement)
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    produit = get_object_or_404(Produit, pk=produit_id)
    if request.method == 'POST':
        produit.delete()
        messages.success(request, "Produit supprimé.")
        return redirect('admin_produits_list')
    # Confirmation simple via la même page liste
    messages.info(request, f"Confirmer la suppression du produit: {produit.nom}")
    return redirect('admin_produits_list')


@login_required
def admin_commandes_list(request):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    qs = Commande.objects.all().select_related('client')
    # Tenter d'inclure le livreur (si le champ existe) pour éviter N+1
    try:
        qs = qs.select_related('livreur__user')
    except Exception:
        pass

    # Filtres
    livree = request.GET.get('livree')  # 'true' | 'false' | None
    if livree in {'true', 'false'}:
        try:
            if livree == 'true':
                qs = qs.filter(statut='livree')
            else:
                qs = qs.exclude(statut='livree')
        except Exception:
            # Si pas de champ statut, ignorer
            pass

    livreur_id = request.GET.get('livreur')
    if livreur_id and livreur_id.isdigit():
        try:
            qs = qs.filter(livreur_id=int(livreur_id))
        except Exception:
            pass

    commandes = qs.order_by('-date_commande')

    # Liste des livreurs pour UI filtre
    try:
        livreurs = ProfilLivreur.objects.select_related('user').order_by('user__username')
    except Exception:
        livreurs = []

    return render(request, 'boutique_admin/commandes_list.html', {
        'commandes': commandes,
        'livree': livree,
        'livreur_id': livreur_id,
        'livreurs': livreurs,
    })


@login_required
def admin_commande_detail(request, commande_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    commande = get_object_or_404(Commande, pk=commande_id)
    items = DetailCommande.objects.filter(commande=commande).select_related('produit')
    livreurs = ProfilLivreur.objects.filter(actif=True).select_related('user').order_by('user__username')
    return render(request, 'boutique_admin/commande_detail.html', {
        'commande': commande,
        'items': items,
        'livreurs': livreurs,
    })


@login_required
def admin_commande_update_statut(request, commande_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    if request.method != 'POST':
        return redirect('admin_commande_detail', commande_id=commande_id)
    commande = get_object_or_404(Commande, pk=commande_id)
    statut = request.POST.get('statut', '').strip()
    try:
        setattr(commande, 'statut', statut)
        commande.save()
        messages.success(request, "Statut mis à jour.")
    except Exception as e:
        messages.error(request, f"Erreur: {e}")
    return redirect('admin_commande_detail', commande_id=commande_id)


@login_required
def admin_commande_assigner_livreur(request, commande_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    if request.method != 'POST':
        return redirect('admin_commande_detail', commande_id=commande_id)
    commande = get_object_or_404(Commande, pk=commande_id)
    livreur_id = request.POST.get('livreur_id')
    try:
        if not hasattr(commande, 'livreur'):
            messages.error(request, "Le modèle Commande n'a pas de champ 'livreur'. Impossible d'assigner.")
        else:
            livreur = get_object_or_404(ProfilLivreur, pk=livreur_id)
            commande.livreur = livreur
            commande.save()
            messages.success(request, "Livreur assigné.")
    except Exception as e:
        messages.error(request, f"Erreur: {e}")
    return redirect('admin_commande_detail', commande_id=commande_id)


@login_required
def admin_clients_list(request):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    clients_qs = ProfilClient.objects.filter(user__is_staff=False, user__is_superuser=False).select_related('user')
    
    clients = list(clients_qs)

    # Fallback: inclure les utilisateurs qui ont passé des commandes mais n'ont pas de ProfilClient
    try:
        # IDs users clients qui ont des commandes
        profile_user_ids = {pc.user_id for pc in clients_qs}
        user_ids_from_orders = set(
            Commande.objects.filter(client__is_staff=False, client__is_superuser=False).values_list('client_id', flat=True).distinct()
        )
        missing_ids = user_ids_from_orders - profile_user_ids
        if missing_ids:
            from types import SimpleNamespace
            for u in get_user_model().objects.filter(id__in=missing_ids, is_staff=False, is_superuser=False):
                clients.append(SimpleNamespace(id=u.id, user=u, telephone=None, adresse=None))
    except Exception:
        pass

    # Option: ordonner par username user
    try:
        clients.sort(key=lambda x: (getattr(getattr(x, 'user', None), 'username', '') or '').lower())
    except Exception:
        pass

    return render(request, 'boutique_admin/clients_list.html', { 'clients': clients })


@login_required
def admin_client_detail(request, client_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    # Résoudre soit un ProfilClient par id, soit un User (fallback)
    profil = None
    user = None
    try:
        profil = ProfilClient.objects.select_related('user').get(pk=client_id)
        user = profil.user
    except ProfilClient.DoesNotExist:
        user = get_object_or_404(get_user_model(), pk=client_id)
        profil = ProfilClient.objects.filter(user=user).first()

    commandes = Commande.objects.filter(client=user).order_by('-id')
    return render(request, 'boutique_admin/client_detail.html', {
        'client': profil or user,  # pour compat template existant
        'user_obj': user,
        'profil': profil,
        'commandes': commandes,
    })


@login_required
def admin_client_toggle_active(request, client_id: int):
    if request.method != 'POST':
        return redirect('admin_client_detail', client_id=client_id)
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    # localiser l'utilisateur
    user = None
    try:
        profil = ProfilClient.objects.select_related('user').get(pk=client_id)
        user = profil.user
    except ProfilClient.DoesNotExist:
        user = get_object_or_404(get_user_model(), pk=client_id)
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    messages.success(request, f"Accès {'activé' if user.is_active else 'désactivé'} pour {user.username}.")
    return redirect('admin_client_detail', client_id=client_id)


@login_required
def admin_client_reset_password(request, client_id: int):
    if request.method != 'POST':
        return redirect('admin_client_detail', client_id=client_id)
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    # localiser l'utilisateur
    try:
        profil = ProfilClient.objects.select_related('user').get(pk=client_id)
        user = profil.user
    except ProfilClient.DoesNotExist:
        user = get_object_or_404(get_user_model(), pk=client_id)
        profil = ProfilClient.objects.filter(user=user).first()
    # Générer un mot de passe temporaire et l'appliquer
    temp_pwd = secrets.token_urlsafe(8)
    user.set_password(temp_pwd)
    user.save(update_fields=['password'])
    messages.success(request, f"Mot de passe réinitialisé. Nouveau mot de passe temporaire: {temp_pwd}")
    # Optionnel: envoyer par email si disponible
    try:
        if user.email:
            subject = "Réinitialisation de votre mot de passe"
            body = (
                f"Bonjour {user.username},\n\n"
                f"Votre mot de passe a été réinitialisé par l'administrateur.\n"
                f"Nouveau mot de passe temporaire: {temp_pwd}\n\n"
                f"Merci de vous connecter et de le changer immédiatement."
            )
            EmailMessage(subject, body, getattr(settings, 'DEFAULT_FROM_EMAIL', None), [user.email]).send(fail_silently=True)
    except Exception:
        pass
    # Rediriger
    return redirect('admin_client_detail', client_id=client_id)


@login_required
def admin_client_delete(request, client_id: int):
    if request.method != 'POST':
        return redirect('admin_client_detail', client_id=client_id)
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    # Par défaut: désactiver le compte utilisateur au lieu de supprimer définitivement (préserve l'historique commandes)
    try:
        profil = ProfilClient.objects.select_related('user').get(pk=client_id)
        user = profil.user
    except ProfilClient.DoesNotExist:
        user = get_object_or_404(get_user_model(), pk=client_id)
    action = request.POST.get('action', 'deactivate')
    if action == 'hard_delete':
        # ATTENTION: cette opération est destructrice, peut casser les FK. À utiliser seulement si sûr.
        try:
            if hasattr(user, 'profillivreur'):
                messages.error(request, "Ce compte est lié à un profil livreur, suppression annulée.")
                return redirect('admin_client_detail', client_id=client_id)
        except Exception:
            pass
        username = user.username
        user.delete()
        messages.success(request, f"Utilisateur {username} supprimé définitivement.")
        return redirect('admin_clients_list')
    else:
        user.is_active = False
        user.save(update_fields=['is_active'])
        messages.success(request, f"Utilisateur {user.username} désactivé (accès refusé).")
        return redirect('admin_client_detail', client_id=client_id)


@login_required
def admin_categories_list(request):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    try:
        categories = Categorie.objects.all().order_by('nom')
    except Exception:
        categories = []
    return render(request, 'boutique_admin/categories_list.html', { 'categories': categories })


@login_required
def admin_categorie_add(request):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        if not nom:
            messages.error(request, "Le nom de la catégorie est requis.")
        else:
            try:
                Categorie.objects.create(nom=nom)
                messages.success(request, "Catégorie créée.")
                return redirect('admin_categories_list')
            except Exception as e:
                messages.error(request, f"Erreur: {e}")
    return render(request, 'boutique_admin/categorie_form.html', { 'mode': 'add' })


@login_required
def admin_categorie_edit(request, categorie_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    categorie = get_object_or_404(Categorie, pk=categorie_id)
    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        if not nom:
            messages.error(request, "Le nom de la catégorie est requis.")
        else:
            try:
                categorie.nom = nom
                categorie.save()
                messages.success(request, "Catégorie modifiée.")
                return redirect('admin_categories_list')
            except Exception as e:
                messages.error(request, f"Erreur: {e}")
    return render(request, 'boutique_admin/categorie_form.html', { 'mode': 'edit', 'categorie': categorie })


@login_required
def admin_categorie_delete(request, categorie_id: int):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')
    categorie = get_object_or_404(Categorie, pk=categorie_id)
    if request.method == 'POST':
        try:
            categorie.delete()
            messages.success(request, "Catégorie supprimée.")
        except Exception as e:
            messages.error(request, f"Erreur: {e}")
        return redirect('admin_categories_list')
    messages.info(request, f"Confirmer la suppression de la catégorie: {categorie.nom}")
    return redirect('admin_categories_list')


# Livreur views

@login_required
def livreur_dashboard(request):
    # Allow in-app admin (or superuser) and active livreur; deny clients
    try:
        is_livreur_actif = hasattr(request.user, 'profillivreur') and bool(request.user.profillivreur.actif)
    except Exception:
        is_livreur_actif = False

    if not (is_app_admin(request.user) or is_livreur_actif):
        messages.error(request, "Accès refusé: réservé au livreur ou à l'administrateur de l'application.")
        return redirect('accueil')

    commandes = []
    is_admin_viewing = False
    if is_livreur_actif:
        livreur = request.user.profillivreur
        try:
            qs = Commande.objects.all().select_related('client')
            # Scope filtre: 'toutes' (default), 'disponibles' (non assignées), 'mes' (assignées à moi)
            scope = request.GET.get('scope', 'toutes')
            if scope == 'disponibles':
                qs = qs.filter(livreur__isnull=True)
            elif scope == 'mes':
                qs = qs.filter(Q(livreur=livreur) | Q(livreur__user=request.user))
            else:  # toutes
                qs = qs.filter(Q(livreur__isnull=True) | Q(livreur=livreur) | Q(livreur__user=request.user))

            inclure_livrees = request.GET.get('inclure_livrees') == 'on'
            if not inclure_livrees:
                qs = qs.exclude(statut='livree')

            commandes = qs.order_by('-date_commande')
        except Exception:
            commandes = []
        if hasattr(commandes, 'count') and commandes.count() == 0:
            messages.info(request, "Aucune commande disponible pour le moment.")
    elif is_app_admin(request.user):
        # Aide au debug: l'admin voit les 50 dernières commandes
        is_admin_viewing = True
        try:
            commandes = Commande.objects.select_related('client').order_by('-date_commande')[:50]
        except Exception:
            commandes = []

    return render(request, "livreur/index.html", {
        "commandes": commandes,
        "is_admin_viewing": is_admin_viewing,
        "nb_commandes": getattr(commandes, 'count', lambda: len(commandes))(),
        "scope": request.GET.get('scope', 'toutes'),
        "inclure_livrees": request.GET.get('inclure_livrees') == 'on',
    })

@login_required
def livreur_accepter_commande(request, commande_id: int):
    # Uniquement livreur actif
    try:
        livreur = request.user.profillivreur
        if not livreur.actif:
            raise AttributeError
    except Exception:
        messages.error(request, "Accès refusé: réservé au livreur actif.")
        return redirect('accueil')

    commande = get_object_or_404(Commande, id=commande_id)
    # Empêcher l'acceptation si déjà livrée
    if getattr(commande, 'statut', None) == 'livree':
        messages.warning(request, "Cette commande est déjà livrée.")
        return redirect('livreur_dashboard')

    # Assignation atomique pour éviter les collisions
    with transaction.atomic():
        c = Commande.objects.select_for_update().get(id=commande.id)
        # Si déjà assignée à un autre livreur, refuser
        try:
            assignation_autre = c.livreur and (c.livreur_id != livreur.id)
        except Exception:
            assignation_autre = False
        if assignation_autre:
            messages.error(request, "Cette commande vient d'être acceptée par un autre livreur.")
            return redirect('livreur_dashboard')

        # Assigner au livreur courant si non assignée ou si déjà à lui
        try:
            c.livreur = livreur
            c.save(update_fields=['livreur'])
        except Exception:
            # Si le champ n'existe pas, avertir
            messages.error(request, "Impossible d'assigner la commande (champ 'livreur' manquant).")
            return redirect('livreur_dashboard')

    messages.success(request, f"Commande #{c.id} acceptée. Vous pouvez désormais confirmer le paiement et livrer.")
    return redirect('livreur_dashboard')

@login_required
def livreur_marquer_livre(request, commande_id: int):
    # Page de confirmation pour marquer une commande comme livrée et confirmer le paiement
    try:
        livreur = request.user.profillivreur
        if not livreur.actif:
            raise AttributeError
    except Exception:
        messages.error(request, "Accès refusé: réservé au livreur actif.")
        return redirect('accueil')

    commande = get_object_or_404(Commande.objects.select_related('client'), id=commande_id)

    # Vérifier que la commande est assignée au livreur courant
    try:
        assign_to_me = (commande.livreur_id == livreur.id)
    except Exception:
        assign_to_me = False

    if not assign_to_me:
        messages.error(request, "Vous n'êtes pas assigné à cette commande.")
        return redirect('livreur_dashboard')

    if request.method == 'POST':
        # Confirmer paiement et livraison
        methode = request.POST.get('payment_method')
        if methode in { 'tMoney', 'flooz', 'cash' }:
            try:
                commande.payment_method = methode
            except Exception:
                pass
        try:
            commande.payment_status = 'paid'
        except Exception:
            pass
        try:
            commande.statut = 'livree'
        except Exception:
            pass
        try:
            from django.utils import timezone
            commande.date_livraison = timezone.now()
        except Exception:
            pass
        # Référence de transaction (optionnelle)
        ref = request.POST.get('transaction_ref')
        if ref:
            for attr in ('payment_reference', 'reference_paiement', 'transaction_ref'):
                try:
                    setattr(commande, attr, ref)
                    break
                except Exception:
                    continue
        # Note livreur (optionnelle)
        note = request.POST.get('note')
        if note:
            for attr in ('note_livreur', 'remarque_livreur', 'commentaire'):
                try:
                    setattr(commande, attr, note)
                    break
                except Exception:
                    continue
        commande.save()
        # 1) Envoyer un message au client avec le lien vers la facture
        try:
            client_user = getattr(commande, 'client', None)
            # Choisir un expéditeur admin si possible
            admin_sender = get_user_model().objects.filter(is_superuser=True).first() or get_user_model().objects.filter(is_staff=True).first() or request.user
            if client_user is not None:
                try:
                    from django.urls import reverse
                    facture_url = reverse('client_facture', args=[commande.numero_commande])
                except Exception:
                    facture_url = f"/facture/{commande.numero_commande}/"
                msg_body = (
                    "Votre commande a été livrée et le paiement confirmé. "
                    f"Votre facture est disponible ici: {facture_url}\n\n"
                    "Merci pour votre achat."
                )
                try:
                    Message.objects.create(sender=admin_sender, recipient=client_user, body=msg_body)
                except Exception:
                    pass
        except Exception:
            pass

        # 2) Notifier l'admin/superuser par email (si configuré) — avant la redirection
        try:
            subject = f"Commande livrée #{commande.id} - {commande.numero_commande}"
            body = render_to_string('emails/commande_livree.txt', {
                'commande': commande,
                'livreur': livreur,
            })
            recipients = list(get_user_model().objects.filter(is_superuser=True, email__isnull=False).values_list('email', flat=True))
            # Si vous avez un ProfilAdmin avec email, on peut l'ajouter ici
            try:
                from .models import ProfilAdmin
                recipients += list(ProfilAdmin.objects.exclude(email__isnull=True).values_list('email', flat=True))
            except Exception:
                pass
            if recipients:
                from django.core.mail import send_mail
                send_mail(subject, body, None, recipients, fail_silently=True)
        except Exception:
            pass

        messages.success(request, "Paiement confirmé et commande marquée comme livrée.")
        # Rester côté livreur: retourner au tableau de bord
        return redirect('livreur_dashboard')

    # GET: afficher la page de confirmation
    return render(request, 'livreur/traiter_commande.html', {
        'commande': commande,
    })

@login_required
def livreur_confirmer_paiement(request, commande_id):
    """Le livreur (assigné) confirme le paiement à la livraison."""
    # Vérifier rôle livreur
    try:
        livreur = request.user.profillivreur
    except ProfilLivreur.DoesNotExist:
        messages.error(request, "Accès réservé aux livreurs.")
        return redirect('livreur_dashboard')

    commande = get_object_or_404(Commande, id=commande_id)
    # Vérifier affectation
    if commande.livreur_id and commande.livreur_id != livreur.id:
        messages.error(request, "Cette commande n'est pas assignée à vous.")
        return redirect('livreur_dashboard')

    # Confirmer paiement et livraison
    commande.payment_status = 'paid'
    commande.statut = 'livree'
    commande.date_livraison = timezone.now()
    if not commande.livreur_id:
        commande.livreur = livreur
    commande.save(update_fields=['payment_status', 'statut', 'date_livraison', 'livreur'])
    messages.success(request, f"Paiement confirmé pour {commande.numero_commande}.")
    return redirect('livreur_dashboard')


@login_required
def admin_ventes_jour(request):
    if not (hasattr(request.user, 'profiladmin') or request.user.is_superuser):
        messages.error(request, "Accès administrateur requis.")
        return redirect('accueil')
    today = timezone.now().date()
    commandes = Commande.objects.filter(payment_status='paid', date_commande__date=today).select_related('client')
    # Recherche simple par numéro de commande ou nom d'utilisateur client
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        commandes = commandes.filter(Q(numero_commande__icontains=q) | Q(client__username__icontains=q))
    total = sum(c.total for c in commandes)
    return render(request, 'boutique_admin/ventes_jour.html', {
        'date': today,
        'commandes': commandes,
        'q': q,
        'total': total,
    })


@login_required
def admin_ventes_semaine(request):
    if not (hasattr(request.user, 'profiladmin') or request.user.is_superuser):
        messages.error(request, "Accès administrateur requis.")
        return redirect('accueil')
    now = timezone.now()
    start = now - timezone.timedelta(days=6)
    commandes = Commande.objects.filter(payment_status='paid', date_commande__date__gte=start.date(), date_commande__date__lte=now.date()).select_related('client').order_by('-date_commande')
    # Recherche simple par numéro de commande ou nom d'utilisateur client
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        commandes = commandes.filter(Q(numero_commande__icontains=q) | Q(client__username__icontains=q))
    total = sum(c.total for c in commandes)
    return render(request, 'boutique_admin/ventes_semaine.html', {
        'start': start.date(),
        'end': now.date(),
        'commandes': commandes,
        'q': q,
        'total': total,
    })


@login_required
def admin_ventes_mois(request):
    if not (hasattr(request.user, 'profiladmin') or request.user.is_superuser):
        messages.error(request, "Accès administrateur requis.")
        return redirect('accueil')
    now = timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    commandes = (
        Commande.objects
        .filter(payment_status='paid',
                date_commande__date__gte=start.date(),
                date_commande__date__lte=now.date())
        .select_related('client')
        .order_by('-date_commande')
    )
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        commandes = commandes.filter(Q(numero_commande__icontains=q) | Q(client__username__icontains=q))
    total = sum(c.total for c in commandes)
    return render(request, 'boutique_admin/ventes_mois.html', {
        'start': start.date(),
        'end': now.date(),
        'commandes': commandes,
        'q': q,
        'total': total,
    })


@login_required
def admin_ventes_annee(request):
    if not (hasattr(request.user, 'profiladmin') or request.user.is_superuser):
        messages.error(request, "Accès administrateur requis.")
        return redirect('accueil')
    now = timezone.now()
    start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    commandes = (
        Commande.objects
        .filter(payment_status='paid',
                date_commande__date__gte=start.date(),
                date_commande__date__lte=now.date())
        .select_related('client')
        .order_by('-date_commande')
    )
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        commandes = commandes.filter(Q(numero_commande__icontains=q) | Q(client__username__icontains=q))
    total = sum(c.total for c in commandes)
    return render(request, 'boutique_admin/ventes_annee.html', {
        'start': start.date(),
        'end': now.date(),
        'commandes': commandes,
        'q': q,
        'total': total,
    })


def is_app_admin(user):
    """Return True if user is allowed to access the in-app admin dashboard.
    - Allowed when the user has an active ProfilAdmin
    - Also allowed if the user is a Django superuser (admin technique)
    The superuser path lets you recover access even if ProfilAdmin is mal configuré.
    """
    if getattr(user, 'is_superuser', False):
        return True
    try:
        return hasattr(user, 'profiladmin') and bool(user.profiladmin.actif)
    except (ProgrammingError, OperationalError):
        # Migrations not applied yet for ProfilAdmin — deny for non-superusers
        return False


@login_required
def admin_messages_diag(request):
    """Page de diagnostic: affiche les 50 derniers messages destinés à des comptes admin/staff."""
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur.")
        return redirect('accueil')
    admins = get_user_model().objects.filter(Q(is_staff=True) | Q(is_superuser=True))
    msgs = (Message.objects.filter(recipient__in=admins)
            .select_related('sender', 'recipient')
            .order_by('-created_at')[:50])
    return render(request, 'boutique_admin/messages_diag.html', {
        'messages_list': msgs,
        'admin_unread_total': Message.objects.filter(recipient=request.user, is_read=False).count(),
    })

@login_required
def admin_stocks(request):
    if not is_app_admin(request.user):
        messages.error(request, "Accès refusé: réservé à l'administrateur de l'application.")
        return redirect('accueil')

    low_threshold = 5

    if request.method == 'POST':
        produit_id = request.POST.get('produit_id')
        action = request.POST.get('action')  # 'set', 'inc', 'dec'
        # Utiliser des champs distincts selon l'action pour éviter conflit de noms dans le template
        qty_raw = request.POST.get('qty_delta') if action in {'inc', 'dec'} else request.POST.get('qty_new')
        try:
            qty = int(qty_raw or 0)
        except (TypeError, ValueError):
            qty = 0
        produit = get_object_or_404(Produit, id=produit_id)
        old_stock = produit.stock
        if action == 'set':
            produit.stock = max(0, qty)
        elif action == 'inc':
            produit.stock = max(0, produit.stock + qty)
        elif action == 'dec':
            produit.stock = max(0, produit.stock - qty)
        produit.save()
        delta = produit.stock - old_stock
        if produit.stock == 0:
            messages.warning(request, f"Stock de '{produit.nom}' mis à {produit.stock}. ATTENTION: stock épuisé !")
        elif produit.stock <= low_threshold:
            messages.warning(request, f"Stock de '{produit.nom}' mis à {produit.stock}. Niveau bas.")
        else:
            messages.success(request, f"Stock de '{produit.nom}' mis à jour (Δ {delta:+}).")
        return redirect('admin_stocks')

    produits = Produit.objects.all().order_by('nom')
    low_count = produits.filter(stock__gt=0, stock__lte=low_threshold, actif=True).count()
    zero_count = produits.filter(stock__lte=0).count()

    # Construire des listes de tâches: ruptures et stocks faibles
    zero_tasks = produits.filter(stock__lte=0).order_by('nom')
    low_tasks = produits.filter(stock__gt=0, stock__lte=low_threshold, actif=True).order_by('stock', 'nom')

    return render(request, 'boutique_admin/stocks.html', {
        'produits': produits,
        'low_threshold': low_threshold,
        'low_count': low_count,
        'zero_count': zero_count,
        'zero_tasks': zero_tasks,
        'low_tasks': low_tasks,
    })
