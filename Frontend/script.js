document.addEventListener('DOMContentLoaded', () => {
    const modal = document.querySelector('#productModal');

    if (!modal) return;

    const title = document.querySelector('#modalTitle');
    const desc = document.querySelector('#modalDescription');
    const price = document.querySelector('#modalPrice');
    const img = document.querySelector('#modalImage');

    document.querySelectorAll('.catalog-card').forEach(card => {
        card.onclick = () => {
            title.textContent = card.dataset.product;
            desc.textContent = card.dataset.description;
            price.textContent = card.dataset.price;

            img.src = card.querySelector('img').src;
            img.alt = card.dataset.product;

            modal.classList.add('open');
        };
    });

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
});