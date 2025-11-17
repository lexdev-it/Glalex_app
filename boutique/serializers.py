from rest_framework import serializers
from .models import Categorie, Produit, Commande, DetailCommande, ProfilClient, ProfilLivreur
from django.contrib.auth.models import User

class CategorieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categorie
        fields = '__all__'

class ProduitSerializer(serializers.ModelSerializer):
    categorie = CategorieSerializer(read_only=True)
    categorie_id = serializers.PrimaryKeyRelatedField(
        source='categorie', queryset=Categorie.objects.all(), write_only=True
    )
    class Meta:
        model = Produit
        fields = ['id','nom','description','prix','stock','categorie','categorie_id','image','actif','date_creation','date_modification']

class CommandeDetailSerializer(serializers.ModelSerializer):
    produit = ProduitSerializer(read_only=True)
    produit_id = serializers.PrimaryKeyRelatedField(source='produit', queryset=Produit.objects.all(), write_only=True)
    class Meta:
        model = DetailCommande
        fields = ['id','produit','produit_id','quantite','prix_unitaire','sous_total']

class CommandeSerializer(serializers.ModelSerializer):
    details = CommandeDetailSerializer(many=True, read_only=True)
    client_username = serializers.CharField(source='client.username', read_only=True)
    class Meta:
        model = Commande
        fields = ['id','numero_commande','client','client_username','livreur','date_commande','date_livraison','statut','total','adresse_livraison','details']

class ProfilClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfilClient
        fields = '__all__'

class ProfilLivreurSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfilLivreur
        fields = '__all__'