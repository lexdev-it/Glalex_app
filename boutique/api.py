from rest_framework import viewsets, permissions
from .models import Categorie, Produit, Commande, DetailCommande, ProfilClient, ProfilLivreur
from .serializers import (
    CategorieSerializer, ProduitSerializer, CommandeSerializer,
    ProfilClientSerializer, ProfilLivreurSerializer
)

class CategorieViewSet(viewsets.ModelViewSet):
    queryset = Categorie.objects.all().order_by('nom')
    serializer_class = CategorieSerializer
    permission_classes = [permissions.AllowAny]

class ProduitViewSet(viewsets.ModelViewSet):
    queryset = Produit.objects.filter(actif=True).order_by('-date_creation')
    serializer_class = ProduitSerializer
    permission_classes = [permissions.AllowAny]

class CommandeViewSet(viewsets.ModelViewSet):
    queryset = Commande.objects.all().order_by('-date_commande')
    serializer_class = CommandeSerializer
    permission_classes = [permissions.IsAuthenticated]

class ProfilClientViewSet(viewsets.ModelViewSet):
    queryset = ProfilClient.objects.all()
    serializer_class = ProfilClientSerializer
    permission_classes = [permissions.IsAdminUser]

class ProfilLivreurViewSet(viewsets.ModelViewSet):
    queryset = ProfilLivreur.objects.all()
    serializer_class = ProfilLivreurSerializer
    permission_classes = [permissions.IsAdminUser]