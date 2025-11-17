from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import Categorie, Produit
from .views import ProduitForm

class ProduitFormTests(TestCase):
    def setUp(self):
        self.cat = Categorie.objects.create(nom="Cat A")

    def test_form_valid_minimal(self):
        form = ProduitForm(data={
            'nom': 'P1',
            'description': 'Desc',
            'prix': '9.99',
            'stock': '5',
            'categorie': self.cat.id,
            'actif': True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        prod = form.save()
        self.assertEqual(prod.stock, 5)

    def test_form_invalid_negative_price(self):
        form = ProduitForm(data={
            'nom': 'P2',
            'description': 'Desc',
            'prix': '-1',
            'stock': '1',
            'categorie': self.cat.id,
            'actif': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('prix', form.errors)

    def test_form_invalid_stock_non_int(self):
        form = ProduitForm(data={
            'nom': 'P3',
            'description': 'Desc',
            'prix': '2.00',
            'stock': 'abc',
            'categorie': self.cat.id,
            'actif': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('stock', form.errors)

    def test_form_invalid_image_too_large(self):
        big_content = b"0" * (2 * 1024 * 1024 + 1)  # > 2MB
        big_file = SimpleUploadedFile("big.jpg", big_content, content_type="image/jpeg")
        form = ProduitForm(data={
            'nom': 'P4',
            'description': 'Desc',
            'prix': '2.00',
            'stock': '1',
            'categorie': self.cat.id,
            'actif': True,
        }, files={'image': big_file})
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)

    def test_form_invalid_image_not_image(self):
        file_content = b"hello world"
        txt_file = SimpleUploadedFile("file.txt", file_content, content_type="text/plain")
        form = ProduitForm(data={
            'nom': 'P5',
            'description': 'Desc',
            'prix': '2.00',
            'stock': '1',
            'categorie': self.cat.id,
            'actif': True,
        }, files={'image': txt_file})
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)

class AdminProduitsListTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="admin", password="pass", email="a@a.com")
        self.cat1 = Categorie.objects.create(nom="Cat 1")
        self.cat2 = Categorie.objects.create(nom="Cat 2")
        for i in range(15):
            Produit.objects.create(
                nom=f"Prod {i}", description="", prix=1.0, stock=i,
                categorie=self.cat1 if i % 2 == 0 else self.cat2, actif=(i % 3 != 0)
            )

    def test_requires_login(self):
        resp = self.client.get(reverse('admin_produits_list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/connexion', resp['Location'])

    def test_paginated_list_as_admin(self):
        self.client.login(username="admin", password="pass")
        resp = self.client.get(reverse('admin_produits_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('page_obj', resp.context)

    def test_filters_work(self):
        self.client.login(username="admin", password="pass")
        # filtre catégorie
        resp = self.client.get(reverse('admin_produits_list'), {'cat': self.cat1.id})
        self.assertEqual(resp.status_code, 200)
        for p in resp.context['produits']:
            self.assertEqual(p.categorie_id, self.cat1.id)
        # filtre actif
        resp2 = self.client.get(reverse('admin_produits_list'), {'actif': '1'})
        self.assertEqual(resp2.status_code, 200)
        for p in resp2.context['produits']:
            self.assertTrue(p.actif)

class AdminProduitsCrudTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="admin", password="pass", email="a@a.com")
        self.client.login(username="admin", password="pass")
        self.cat = Categorie.objects.create(nom="Cat A")

    def test_add_product_with_image(self):
        img_content = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        image = SimpleUploadedFile("tiny.gif", img_content, content_type="image/gif")
        resp = self.client.post(reverse('admin_produit_add'), data={
            'nom': 'Nouveau',
            'description': 'Desc',
            'prix': '3.50',
            'stock': '4',
            'categorie': self.cat.id,
            'actif': 'on',
            'image': image,
        })
        self.assertEqual(resp.status_code, 302)
        p = Produit.objects.get(nom='Nouveau')
        self.assertTrue(bool(p.image))

    def test_edit_product_clear_image(self):
        # créer un produit avec image
        img_content = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        image = SimpleUploadedFile("tiny.gif", img_content, content_type="image/gif")
        p = Produit.objects.create(nom='ProdX', description='', prix=1.0, stock=1, categorie=self.cat, actif=True, image=image)
        self.assertTrue(bool(p.image))
        # clear_image
        resp = self.client.post(reverse('admin_produit_edit', args=[p.id]), data={
            'nom': 'ProdX',
            'description': '',
            'prix': '1.00',
            'stock': '1',
            'categorie': self.cat.id,
            'actif': 'on',
            'clear_image': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertFalse(bool(p.image))

    def test_delete_product(self):
        p = Produit.objects.create(nom='ASupprimer', description='', prix=1.0, stock=0, categorie=self.cat, actif=True)
        resp = self.client.post(reverse('admin_produit_delete', args=[p.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Produit.objects.filter(id=p.id).exists())
