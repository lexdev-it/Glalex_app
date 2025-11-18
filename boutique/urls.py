from django.urls import path
from django.views.generic.base import RedirectView
from . import views

urlpatterns = [
    # URLs générales
    path('', views.accueil, name='accueil'),
    path('connexion/', views.login_view, name='connexion'),
    path('inscription/', views.register, name='inscription'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),

    # URLs Client
    path('boutique/', views.client_boutique, name='client_boutique'),
    path('panier/', views.view_cart, name='view_cart'),
    path('panier/update/<int:produit_id>/', views.cart_update, name='cart_update'),
    path('panier/remove/<int:produit_id>/', views.cart_remove, name='cart_remove'),
    path('ajouter-panier/<int:produit_id>/', views.add_to_cart, name='add_to_cart'),
    path('valider-panier/', views.client_checkout, name='checkout'),
    path('facture/<str:numero>/', views.client_facture, name='client_facture'),
    path('facture/<str:numero>/pdf/', views.client_facture_pdf, name='client_facture_pdf'),
    path('paiement/<str:numero>/', views.client_paiement, name='client_paiement'),
    path('mes-commandes/', views.client_commandes, name='client_commandes'),
    path('messages/', views.client_messages, name='client_messages'),
    path('suggestions/', views.client_suggestions, name='client_suggestions'),

    # URLs Admin (in-app)
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/ventes/jour/', views.admin_ventes_jour, name='admin_ventes_jour'),
    path('admin-dashboard/ventes/semaine/', views.admin_ventes_semaine, name='admin_ventes_semaine'),
    path('admin-dashboard/ventes/mois/', views.admin_ventes_mois, name='admin_ventes_mois'),
    path('admin-dashboard/ventes/annee/', views.admin_ventes_annee, name='admin_ventes_annee'),
    path('admin-dashboard/messages/', views.admin_inbox, name='admin_inbox'),
    path('admin-dashboard/messages/diag/', views.admin_messages_diag, name='admin_messages_diag'),
    path('admin-dashboard/messages/<int:client_id>/', views.admin_messages, name='admin_messages'),
    path('admin-dashboard/messages/livreur/<int:livreur_id>/', views.admin_livreur_messages, name='admin_livreur_messages'),

    # Legacy redirects from old '/admin/...' to in-app admin dashboard
    path('admin/livreurs/ajouter/', RedirectView.as_view(url='/admin-dashboard/livreurs/ajouter/', permanent=False)),
    path('admin/livreurs/', RedirectView.as_view(url='/admin-dashboard/livreurs/', permanent=False)),
    path('admin/produits/ajouter/', RedirectView.as_view(url='/admin-dashboard/produits/ajouter/', permanent=False)),
    path('admin/produits/', RedirectView.as_view(url='/admin-dashboard/produits/', permanent=False)),
    path('admin/commandes/', RedirectView.as_view(url='/admin-dashboard/commandes/', permanent=False)),
    path('admin/clients/', RedirectView.as_view(url='/admin-dashboard/clients/', permanent=False)),

    # Produits (CRUD)
    path('admin-dashboard/produits/', views.admin_produits_list, name='admin_produits_list'),
    path('admin-dashboard/produits/ajouter/', views.admin_produit_add, name='admin_produit_add'),
    path('admin-dashboard/produits/<int:produit_id>/modifier/', views.admin_produit_edit, name='admin_produit_edit'),
    path('admin-dashboard/produits/<int:produit_id>/supprimer/', views.admin_produit_delete, name='admin_produit_delete'),

    # Livreurs (existant)
    path('admin-dashboard/livreurs/', views.admin_livreurs_list, name='admin_livreurs_list'),
    path('admin-dashboard/livreurs/ajouter/', views.admin_livreur_add, name='admin_livreur_add'),
    path('admin-dashboard/livreurs/<int:livreur_id>/modifier/', views.admin_livreur_edit, name='admin_livreur_edit'),
    path('admin-dashboard/livreurs/<int:livreur_id>/supprimer/', views.admin_livreur_delete, name='admin_livreur_delete'),
    path('admin-dashboard/livreurs/<int:livreur_id>/reset-password/', views.admin_livreur_reset_password, name='admin_livreur_reset_password'),
    path('admin-dashboard/livreurs/<int:livreur_id>/set-password/', views.admin_livreur_set_password, name='admin_livreur_set_password'),

    # Commandes & Clients (listing initial)
    path('admin-dashboard/commandes/', views.admin_commandes_list, name='admin_commandes_list'),
    path('admin-dashboard/commandes/<int:commande_id>/', views.admin_commande_detail, name='admin_commande_detail'),
    path('admin-dashboard/commandes/<int:commande_id>/statut/', views.admin_commande_update_statut, name='admin_commande_update_statut'),
    path('admin-dashboard/commandes/<int:commande_id>/assigner-livreur/', views.admin_commande_assigner_livreur, name='admin_commande_assigner_livreur'),
    path('admin-dashboard/clients/', views.admin_clients_list, name='admin_clients_list'),
    path('admin-dashboard/clients/<int:client_id>/', views.admin_client_detail, name='admin_client_detail'),
    path('admin-dashboard/clients/<int:client_id>/toggle-active/', views.admin_client_toggle_active, name='admin_client_toggle_active'),
    path('admin-dashboard/clients/<int:client_id>/reset-password/', views.admin_client_reset_password, name='admin_client_reset_password'),
    path('admin-dashboard/clients/<int:client_id>/delete/', views.admin_client_delete, name='admin_client_delete'),

    # Categories (CRUD)
    path('admin-dashboard/categories/', views.admin_categories_list, name='admin_categories_list'),
    path('admin-dashboard/categories/ajouter/', views.admin_categorie_add, name='admin_categorie_add'),
    path('admin-dashboard/categories/<int:categorie_id>/modifier/', views.admin_categorie_edit, name='admin_categorie_edit'),
    path('admin-dashboard/categories/<int:categorie_id>/supprimer/', views.admin_categorie_delete, name='admin_categorie_delete'),

    # Stocks
    path('admin-dashboard/stocks/', views.admin_stocks, name='admin_stocks'),

    # URLs Livreur
    path('livreur/', views.livreur_dashboard, name='livreur_dashboard'),
    path('livreur/messages/', views.livreur_messages, name='livreur_messages'),
    path('livreur/accepter/<int:commande_id>/', views.livreur_accepter_commande, name='livreur_accepter_commande'),
    path('livreur/livrer/<int:commande_id>/', views.livreur_marquer_livre, name='livreur_marquer_livre'),
    path('livreur/confirm-paiement/<int:commande_id>/', views.livreur_confirmer_paiement, name='livreur_confirmer_paiement'),
]
