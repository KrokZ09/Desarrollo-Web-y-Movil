document.addEventListener('DOMContentLoaded', async () => {
    const modal = document.querySelector('#productModal');

    if (!modal) return; // solo la página de productos tiene modal y catálogo

    const catalog = document.querySelector('#catalog');
    const title = document.querySelector('#modalTitle');
    const desc = document.querySelector('#modalDescription');
    const price = document.querySelector('#modalPrice');
    const img = document.querySelector('#modalImage');
    const buyButton = modal.querySelector('.buy-btn');

    const close = () => {
        modal.classList.remove('open');
    };

    document.querySelector('.modal-close').onclick = close;

    modal.onclick = event => {
        if (event.target === modal) {
            close();
        }
    };

    document.onkeydown = event => {
        if (event.key === 'Escape') {
            close();
        }
    };

    function openProduct(product, imageSrc) {
        // textContent (y no innerHTML): los datos del servidor se muestran como texto, nunca como HTML
        title.textContent = product.nombre;
        desc.textContent = product.descripcion;
        price.textContent = formatPrice(product.precio);

        img.src = imageSrc;
        img.alt = product.nombre;

        buyButton.disabled = !product.disponible;
        buyButton.textContent = product.disponible ? 'Agregar a compra' : 'No disponible';

        modal.classList.add('open');
    }

    function renderCard(product) {
        const card = document.createElement('article');
        card.className = 'catalog-card';

        const image = document.createElement('img');
        image.src = 'assets/placeholder.png';
        image.alt = product.nombre;

        const info = document.createElement('div');
        const name = document.createElement('h2');
        name.textContent = product.nombre;
        const cost = document.createElement('p');
        cost.textContent = formatPrice(product.precio);
        info.append(name, cost);

        card.append(image, info);
        card.onclick = () => openProduct(product, image.src);
        return card;
    }

    function showMessage(text) {
        const message = document.createElement('p');
        message.className = 'status-msg';
        message.textContent = text;
        catalog.replaceChildren(message);
    }

    try {
        const products = await api('/products');

        if (products.length === 0) {
            showMessage('Todavía no hay productos disponibles.');
        } else {
            catalog.replaceChildren(...products.map(renderCard));
        }
    } catch (error) {
        showMessage('No pudimos cargar los productos. Intenta de nuevo más tarde.');
    }
});
