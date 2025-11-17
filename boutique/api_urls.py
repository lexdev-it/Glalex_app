from rest_framework.routers import DefaultRouter
from .api import (
    CategorieViewSet, ProduitViewSet, CommandeViewSet,
    ProfilClientViewSet, ProfilLivreurViewSet
)

router = DefaultRouter()
router.register(r'categories', CategorieViewSet, basename='categories')
router.register(r'produits', ProduitViewSet, basename='produits')
router.register(r'commandes', CommandeViewSet, basename='commandes')
router.register(r'profils-clients', ProfilClientViewSet, basename='profils-clients')
router.register(r'profils-livreurs', ProfilLivreurViewSet, basename='profils-livreurs')

urlpatterns = router.urls