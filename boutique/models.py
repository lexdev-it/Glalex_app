from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# Modèle pour les catégories de produits
class Categorie(models.Model):
    nom = models.CharField(max_length=100, verbose_name="Nom de la catégorie")
    description = models.TextField(blank=True, verbose_name="Description")
    date_creation = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"
    
    def __str__(self):
        return self.nom

# Modèle pour les produits
class Produit(models.Model):
    nom = models.CharField(max_length=200, verbose_name="Nom du produit")
    description = models.TextField(verbose_name="Description")
    prix = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix")
    stock = models.PositiveIntegerField(default=0, verbose_name="Stock disponible")
    categorie = models.ForeignKey(Categorie, on_delete=models.CASCADE, verbose_name="Catégorie")
    image = models.ImageField(upload_to='produits/', blank=True, null=True, verbose_name="Image")
    actif = models.BooleanField(default=True, verbose_name="Produit actif")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ['-date_creation']
    
    def __str__(self):
        return self.nom

# Modèle pour le profil client
class ProfilClient(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Utilisateur")
    telephone = models.CharField(max_length=15, blank=True, verbose_name="Téléphone")
    adresse = models.TextField(blank=True, verbose_name="Adresse")
    ville = models.CharField(max_length=100, blank=True, verbose_name="Ville")
    code_postal = models.CharField(max_length=10, blank=True, verbose_name="Code postal")
    date_naissance = models.DateField(blank=True, null=True, verbose_name="Date de naissance")
    
    class Meta:
        verbose_name = "Profil Client"
        verbose_name_plural = "Profils Clients"
    
    def __str__(self):
        return f"Profil de {self.user.username}"

# Modèle pour le profil livreur
class ProfilLivreur(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Utilisateur")
    telephone = models.CharField(max_length=15, verbose_name="Téléphone")
    vehicule = models.CharField(max_length=100, verbose_name="Type de véhicule")
    numero_permis = models.CharField(max_length=20, verbose_name="Numéro de permis")
    zone_livraison = models.CharField(max_length=200, verbose_name="Zone de livraison")
    actif = models.BooleanField(default=True, verbose_name="Livreur actif")
    date_embauche = models.DateField(auto_now_add=True, verbose_name="Date d'embauche")
    photo = models.ImageField(upload_to='livreurs/', blank=True, null=True, verbose_name="Photo")
    
    class Meta:
        verbose_name = "Profil Livreur"
        verbose_name_plural = "Profils Livreurs"
    
    def __str__(self):
        return f"Livreur {self.user.username}"

# Modèle pour le profil admin
class ProfilAdmin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profiladmin')
    actif = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Admin: {self.user.username} ({'actif' if self.actif else 'inactif'})"

# Modèle pour les commandes
class Commande(models.Model):
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('confirmee', 'Confirmée'),
        ('expediee', 'Expédiée'),
        ('livree', 'Livrée'),
        ('annulee', 'Annulée'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('tmoney', 'TMoney'),
        ('flooz', 'Flooz'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'En attente de paiement'),
        ('paid', 'Payé'),
        ('failed', 'Échoué'),
    ]
    
    client = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Client")
    livreur = models.ForeignKey(ProfilLivreur, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Livreur assigné")
    numero_commande = models.CharField(max_length=20, unique=True, verbose_name="Numéro de commande")
    date_commande = models.DateTimeField(default=timezone.now, verbose_name="Date de commande")
    date_livraison = models.DateTimeField(null=True, blank=True, verbose_name="Date de livraison")
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente', verbose_name="Statut")
    total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total")
    adresse_livraison = models.TextField(verbose_name="Adresse de livraison")
    nom_complet = models.CharField(max_length=150, verbose_name="Nom complet")
    telephone = models.CharField(max_length=30, verbose_name="Téléphone")
    ville = models.CharField(max_length=100, blank=True, verbose_name="Ville")
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, null=True, blank=True, verbose_name="Moyen de paiement")
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='pending', verbose_name="Statut paiement")
    
    class Meta:
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"
        ordering = ['-date_commande']
    
    def __str__(self):
        return f"Commande {self.numero_commande} - {self.client.username}"

# Modèle pour les détails de commande
class DetailCommande(models.Model):
    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name='details', verbose_name="Commande")
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, verbose_name="Produit")
    quantite = models.PositiveIntegerField(verbose_name="Quantité")
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix unitaire")
    
    class Meta:
        verbose_name = "Détail de commande"
        verbose_name_plural = "Détails de commandes"
    
    def __str__(self):
        return f"{self.produit.nom} x {self.quantite}"
    
    @property
    def sous_total(self):
        return self.quantite * self.prix_unitaire

# Modèle pour les messages
class Message(models.Model):
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='received_messages', on_delete=models.CASCADE)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Msg from {self.sender} to {self.recipient} at {self.created_at:%Y-%m-%d %H:%M}"
