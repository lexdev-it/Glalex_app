from django.contrib import admin
from .models import Categorie, Produit, ProfilClient, ProfilLivreur, ProfilAdmin, Commande, DetailCommande


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ("nom", "date_creation")
    search_fields = ("nom",)


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ("nom", "categorie", "prix", "stock", "actif")
    list_filter = ("categorie", "actif")
    search_fields = ("nom", "description")


@admin.register(ProfilClient)
class ProfilClientAdmin(admin.ModelAdmin):
    list_display = ("user", "telephone", "ville")
    search_fields = ("user__username", "telephone")


@admin.register(ProfilLivreur)
class ProfilLivreurAdmin(admin.ModelAdmin):
    list_display = ("user", "telephone", "vehicule", "zone_livraison", "actif")
    list_filter = ("actif",)
    search_fields = ("user__username", "telephone", "zone_livraison")


@admin.register(ProfilAdmin)
class ProfilAdminAdmin(admin.ModelAdmin):
    list_display = ("user", "actif")
    list_filter = ("actif",)
    search_fields = ("user__username",)


class DetailCommandeInline(admin.TabularInline):
    model = DetailCommande
    extra = 0


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ("numero_commande", "client", "statut", "total", "date_commande")
    list_filter = ("statut", "date_commande")
    search_fields = ("numero_commande", "client__username")
    inlines = [DetailCommandeInline]

    def save_model(self, request, obj, form, change):
        if not obj.numero_commande:
            # Générer un numéro de commande automatique
            import uuid
            obj.numero_commande = f"CMD-{uuid.uuid4().hex[:8].upper()}"
        super().save_model(request, obj, form, change)
