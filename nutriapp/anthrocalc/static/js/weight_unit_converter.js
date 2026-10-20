/**
 * Weight Unit Converter Module for Nutriacción
 * Handles bidirectional conversion between kilograms (kg) and pounds (lb),
 * live visual feedback badges, and DOM synchronization for Django forms.
 *
 * Standard constant: 1 lb = 0.45359237 kg
 */
(function(window) {
    'use strict';

    const LB_TO_KG = 0.45359237;
    const KG_TO_LB = 1 / LB_TO_KG;
    const STORAGE_KEY = 'nutriapp_preferred_weight_unit';

    /**
     * Parses numeric value from string or number, supporting comma and dot decimals.
     * @param {string|number} val
     * @returns {number|null}
     */
    function parseWeight(val) {
        if (val === null || val === undefined) return null;
        if (typeof val === 'number') return isNaN(val) ? null : val;
        const cleaned = String(val).trim().replace(',', '.');
        if (cleaned === '') return null;
        const num = parseFloat(cleaned);
        return isNaN(num) ? null : num;
    }

    /**
     * Converts pounds (lb) to kilograms (kg), rounded to 2 decimal places.
     * @param {string|number} lb
     * @returns {number|null}
     */
    function lbToKg(lb) {
        const val = parseWeight(lb);
        if (val === null) return null;
        return Math.round(val * LB_TO_KG * 100) / 100;
    }

    /**
     * Converts kilograms (kg) to pounds (lb), rounded to 2 decimal places.
     * @param {string|number} kg
     * @returns {number|null}
     */
    function kgToLb(kg) {
        const val = parseWeight(kg);
        if (val === null) return null;
        return Math.round(val * KG_TO_LB * 100) / 100;
    }

    /**
     * Formats number to fixed 2 decimal places string or empty string if null.
     * @param {number|null} val
     * @returns {string}
     */
    function formatWeight(val) {
        if (val === null || val === undefined || isNaN(val)) return '';
        return Number(val).toFixed(2);
    }

    /**
     * Retrieves stored unit preference ('kg' or 'lb').
     * @returns {string}
     */
    function getPreferredUnit() {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            return (stored === 'lb') ? 'lb' : 'kg';
        } catch (e) {
            return 'kg';
        }
    }

    /**
     * Saves unit preference to localStorage.
     * @param {string} unit ('kg' or 'lb')
     */
    function setPreferredUnit(unit) {
        try {
            if (unit === 'lb' || unit === 'kg') {
                localStorage.setItem(STORAGE_KEY, unit);
            }
        } catch (e) {
            // Ignore localStorage errors (e.g. private mode)
        }
    }

    /**
     * Checks if a kg value is within plausible physiological range (0.5 kg - 150 kg).
     * @param {number} kgVal
     * @returns {boolean}
     */
    function isPlausibleKg(kgVal) {
        return kgVal >= 0.5 && kgVal <= 150.0;
    }

    /**
     * Attaches conversion and toggle logic to a single form input.
     * @param {Object} options
     * @param {HTMLInputElement} options.input - The weight input field
     * @param {HTMLElement} [options.toggleContainer] - Container with [data-unit] buttons
     * @param {HTMLElement} [options.feedbackBadge] - Element to display equivalent value
     * @param {HTMLFormElement} [options.form] - Parent form
     */
    function attachIndividualInput(options) {
        const input = options.input;
        if (!input || input.dataset.weightConverterAttached === 'true') return;
        input.dataset.weightConverterAttached = 'true';

        const form = options.form || input.closest('form');
        let currentUnit = 'kg';

        // Find or create UI elements if not passed
        let toggleContainer = options.toggleContainer;
        let feedbackBadge = options.feedbackBadge;

        if (!toggleContainer) {
            const wrapper = document.createElement('div');
            wrapper.className = 'input-group mb-1 weight-unit-input-group';
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(input);

            toggleContainer = document.createElement('div');
            toggleContainer.className = 'btn-group btn-group-sm weight-unit-toggle';
            toggleContainer.setAttribute('role', 'group');
            toggleContainer.setAttribute('aria-label', 'Unidad de peso');
            toggleContainer.innerHTML = `
                <button type="button" class="btn btn-outline-primary active" data-unit="kg">kg</button>
                <button type="button" class="btn btn-outline-primary" data-unit="lb">lb</button>
            `;
            wrapper.appendChild(toggleContainer);
        }

        if (!feedbackBadge) {
            feedbackBadge = document.createElement('div');
            feedbackBadge.className = 'weight-conversion-feedback form-text mt-1 text-muted';
            feedbackBadge.style.minHeight = '1.25rem';
            const parent = input.closest('.weight-unit-input-group') || input;
            if (parent.parentNode) {
                parent.parentNode.insertBefore(feedbackBadge, parent.nextSibling);
            }
        }

        function updateFeedback() {
            const rawVal = input.value.trim();
            if (!rawVal) {
                feedbackBadge.innerHTML = '';
                return;
            }

            const num = parseWeight(rawVal);
            if (num === null) {
                feedbackBadge.innerHTML = '<span class="text-danger small">Valor numérico inválido</span>';
                return;
            }

            if (currentUnit === 'lb') {
                const kgVal = lbToKg(num);
                const plausible = isPlausibleKg(kgVal);
                const badgeClass = plausible ? 'badge bg-secondary' : 'badge bg-warning text-dark';
                const warningMsg = !plausible ? ' <span class="text-warning small">(Fuera de rango habitual 0.5-150 kg)</span>' : '';
                feedbackBadge.innerHTML = `<span class="${badgeClass}">≈ ${formatWeight(kgVal)} kg</span>${warningMsg}`;
            } else {
                const lbVal = kgToLb(num);
                feedbackBadge.innerHTML = `<span class="badge bg-light text-muted border">≈ ${formatWeight(lbVal)} lb</span>`;
            }
        }

        function setUnit(newUnit, convertExistingValue = true) {
            if (newUnit !== 'kg' && newUnit !== 'lb') return;
            const prevUnit = currentUnit;
            currentUnit = newUnit;
            input.dataset.activeUnit = newUnit;

            // Update toggle buttons active state
            if (toggleContainer) {
                toggleContainer.querySelectorAll('[data-unit]').forEach(btn => {
                    if (btn.getAttribute('data-unit') === newUnit) {
                        btn.classList.add('active', 'btn-primary');
                        btn.classList.remove('btn-outline-primary');
                    } else {
                        btn.classList.remove('active', 'btn-primary');
                        btn.classList.add('btn-outline-primary');
                    }
                });
            }

            // Update input placeholder
            input.placeholder = newUnit;

            // Convert existing value if requested
            if (convertExistingValue && prevUnit !== newUnit) {
                const rawVal = input.value.trim();
                if (rawVal) {
                    const parsed = parseWeight(rawVal);
                    if (parsed !== null) {
                        if (newUnit === 'lb') {
                            input.value = formatWeight(kgToLb(parsed));
                        } else {
                            input.value = formatWeight(lbToKg(parsed));
                        }
                    }
                }
            }

            updateFeedback();
        }

        // Toggle click handler
        if (toggleContainer) {
            toggleContainer.addEventListener('click', function(e) {
                const target = e.target.closest('[data-unit]');
                if (target) {
                    e.preventDefault();
                    const selectedUnit = target.getAttribute('data-unit');
                    setPreferredUnit(selectedUnit);
                    setUnit(selectedUnit, true);
                }
            });
        }

        // Input change handlers
        input.addEventListener('input', updateFeedback);
        input.addEventListener('change', updateFeedback);

        // Form submit handler: convert lb values to kg before submitting
        if (form) {
            form.addEventListener('submit', function() {
                if (currentUnit === 'lb') {
                    const rawVal = input.value.trim();
                    if (rawVal) {
                        const parsed = parseWeight(rawVal);
                        if (parsed !== null) {
                            const kgVal = lbToKg(parsed);
                            input.value = formatWeight(kgVal);
                        }
                    }
                }
            });
        }

        // Initial setup from preference or server-rendered kg value
        const initialPref = getPreferredUnit();
        if (initialPref === 'lb') {
            // If the field already has a value from Django (which is in kg), convert it to lb for display
            const initialKgVal = input.value.trim();
            setUnit('lb', false);
            if (initialKgVal) {
                const parsed = parseWeight(initialKgVal);
                if (parsed !== null) {
                    input.value = formatWeight(kgToLb(parsed));
                }
            }
            updateFeedback();
        } else {
            setUnit('kg', false);
            updateFeedback();
        }

        return {
            setUnit,
            getUnit: () => currentUnit,
            updateFeedback
        };
    }

    /**
     * Attaches master column toggle and row conversion handlers to the Mass Visit Grid.
     * @param {Object} options
     * @param {HTMLTableElement} options.table - The #massEntryTable element
     * @param {HTMLElement} [options.masterToggle] - Master toggle element with [data-unit]
     * @param {HTMLFormElement} [options.form] - The #massVisitForm element
     */
    function attachMassVisitTable(options) {
        const table = options.table || document.getElementById('massEntryTable');
        if (!table || table.dataset.weightConverterAttached === 'true') return;
        table.dataset.weightConverterAttached = 'true';

        const form = options.form || document.getElementById('massVisitForm') || table.closest('form');
        let masterToggle = options.masterToggle || document.getElementById('mass-unit-toggle');
        let currentUnit = 'kg';

        function getAllWeightInputs() {
            return table.querySelectorAll('input[name$="-weight"]');
        }

        function updateRowFeedback(input) {
            let rowFeedback = input.parentElement.querySelector('.weight-row-feedback');
            if (!rowFeedback) {
                rowFeedback = document.createElement('div');
                rowFeedback.className = 'weight-row-feedback text-muted small mt-1';
                rowFeedback.style.fontSize = '0.75rem';
                input.parentElement.appendChild(rowFeedback);
            }

            const rawVal = input.value.trim();
            if (!rawVal) {
                rowFeedback.innerHTML = '';
                return;
            }

            const num = parseWeight(rawVal);
            if (num === null) {
                rowFeedback.innerHTML = '<span class="text-danger">Inválido</span>';
                return;
            }

            if (currentUnit === 'lb') {
                const kgVal = lbToKg(num);
                const plausible = isPlausibleKg(kgVal);
                const badgeClass = plausible ? 'badge bg-secondary' : 'badge bg-warning text-dark';
                rowFeedback.innerHTML = `<span class="${badgeClass}">≈ ${formatWeight(kgVal)} kg</span>`;
            } else {
                rowFeedback.innerHTML = '';
            }
        }

        function setTableUnit(newUnit, convertExistingValues = true) {
            if (newUnit !== 'kg' && newUnit !== 'lb') return;
            const prevUnit = currentUnit;
            currentUnit = newUnit;

            // Update master toggle buttons
            if (masterToggle) {
                masterToggle.querySelectorAll('[data-unit]').forEach(btn => {
                    if (btn.getAttribute('data-unit') === newUnit) {
                        btn.classList.add('active', 'btn-primary');
                        btn.classList.remove('btn-outline-light', 'btn-outline-primary');
                    } else {
                        btn.classList.remove('active', 'btn-primary');
                        btn.classList.add('btn-outline-light');
                    }
                });
            }

            // Update all weight column headers and inputs
            const inputs = getAllWeightInputs();
            inputs.forEach(input => {
                input.placeholder = newUnit;
                if (convertExistingValues && prevUnit !== newUnit) {
                    const rawVal = input.value.trim();
                    if (rawVal) {
                        const parsed = parseWeight(rawVal);
                        if (parsed !== null) {
                            if (newUnit === 'lb') {
                                input.value = formatWeight(kgToLb(parsed));
                            } else {
                                input.value = formatWeight(lbToKg(parsed));
                            }
                        }
                    }
                }
                updateRowFeedback(input);
            });
        }

        // Master toggle click handler
        if (masterToggle) {
            masterToggle.addEventListener('click', function(e) {
                const target = e.target.closest('[data-unit]');
                if (target) {
                    e.preventDefault();
                    const selectedUnit = target.getAttribute('data-unit');
                    setPreferredUnit(selectedUnit);
                    setTableUnit(selectedUnit, true);
                }
            });
        }

        // Event delegation for table inputs
        table.addEventListener('input', function(e) {
            if (e.target && e.target.matches('input[name$="-weight"]')) {
                updateRowFeedback(e.target);
            }
        });
        table.addEventListener('change', function(e) {
            if (e.target && e.target.matches('input[name$="-weight"]')) {
                updateRowFeedback(e.target);
            }
        });

        // Form submit handler: convert all inputs to kg before submission
        if (form) {
            form.addEventListener('submit', function() {
                if (currentUnit === 'lb') {
                    const inputs = getAllWeightInputs();
                    inputs.forEach(input => {
                        const rawVal = input.value.trim();
                        if (rawVal) {
                            const parsed = parseWeight(rawVal);
                            if (parsed !== null) {
                                input.value = formatWeight(lbToKg(parsed));
                            }
                        }
                    });
                }
            });
        }

        // Initial setup from preference or server-rendered values
        const initialPref = getPreferredUnit();
        if (initialPref === 'lb') {
            setTableUnit('lb', false);
            // Convert any initial server-rendered kg values to lb for display
            getAllWeightInputs().forEach(input => {
                const initialKgVal = input.value.trim();
                if (initialKgVal) {
                    const parsed = parseWeight(initialKgVal);
                    if (parsed !== null) {
                        input.value = formatWeight(kgToLb(parsed));
                    }
                }
                updateRowFeedback(input);
            });
        } else {
            setTableUnit('kg', false);
            getAllWeightInputs().forEach(input => updateRowFeedback(input));
        }

        return {
            setTableUnit,
            getTableUnit: () => currentUnit,
            refreshFeedback: () => getAllWeightInputs().forEach(input => updateRowFeedback(input))
        };
    }

    /**
     * Automatic initializer on DOM ready.
     */
    function autoInit() {
        // Individual Metric form weight field
        const metricWeightInput = document.getElementById('id_weight');
        if (metricWeightInput) {
            attachIndividualInput({ input: metricWeightInput });
        }

        // Patient form birth_weight field
        const birthWeightInput = document.getElementById('id_birth_weight');
        if (birthWeightInput) {
            attachIndividualInput({ input: birthWeightInput });
        }

        // Mass visit grid
        const massTable = document.getElementById('massEntryTable');
        if (massTable) {
            attachMassVisitTable({ table: massTable });
        }
    }

    if (typeof document !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', autoInit);
        } else {
            autoInit();
        }
    }

    // Export module to global scope
    window.WeightUnitConverter = {
        LB_TO_KG,
        KG_TO_LB,
        parseWeight,
        lbToKg,
        kgToLb,
        formatWeight,
        getPreferredUnit,
        setPreferredUnit,
        isPlausibleKg,
        attachIndividualInput,
        attachMassVisitTable,
        autoInit
    };

})(typeof window !== 'undefined' ? window : this);
