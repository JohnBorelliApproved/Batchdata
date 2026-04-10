document.addEventListener('DOMContentLoaded', () => {
    const searchForm = document.getElementById('search-form');
    const distributeForm = document.getElementById('distribute-form');
    const responseContainer = document.getElementById('response-container');

    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const zip_codes = document.getElementById('zip_codes').value.split(',').map(z => z.trim()).filter(z => z);
        const city = document.getElementById('city').value.trim();
        const state = document.getElementById('state').value.trim();

        const body = {};
        if (zip_codes.length > 0) body.zip_codes = zip_codes;
        if (city) body.city = city;
        if (state) body.state = state;

        try {
            const response = await fetch('/start-search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const result = await response.json();
            responseContainer.textContent = JSON.stringify(result, null, 2);
        } catch (error) {
            responseContainer.textContent = `Error: ${error.message}`;
        }
    });

    distributeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const source_location_id = document.getElementById('source_location_id').value.trim();
        const location_id = document.getElementById('location_id').value.trim();
        const tag = document.getElementById('tag').value.trim();

        const body = { source_location_id, location_id, tag };

        try {
            const response = await fetch('/distribute-contacts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const result = await response.json();
            responseContainer.textContent = JSON.stringify(result, null, 2);
        } catch (error) {
            responseContainer.textContent = `Error: ${error.message}`;
        }
    });
});
