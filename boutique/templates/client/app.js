async function chargerProduits() {
    const res = await fetch('/api/produits/');
    const produits = await res.json();
    const cont = document.getElementById('produits');
    cont.innerHTML = produits.map(p => `
      <div class="card">
        <h3>${p.nom}</h3>
        <p>${p.description}</p>
        <strong>${p.prix} FCFA</strong>
      </div>
    `).join('');
  }
  document.addEventListener('DOMContentLoaded', chargerProduits);