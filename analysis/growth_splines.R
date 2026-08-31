# Subject-specific childhood growth curve, following:
#   Grajeda, Ivanescu, Saito, Crainiceanu, Jaganath et al. (2016)
#   "Modelling subject-specific childhood growth using linear mixed-effect
#   models with cubic regression splines." Emerging Themes in Epidemiology 13:1.
#
# Adapted to this project's export schema (parquet/csv from
# `python manage.py export_longform`), not the original .dta cohort file.
# Column mapping vs. the paper's variable names:
#   id.num -> patient_id      t -> age_months      height -> height
#   ma0fe1 -> gender == "F"   I(t>24) -> paper's proxy; we also have the
#   real per-visit `standing_or_upright` flag, which is better data.
#
# Verified against a synthetic 12-patient / 132-visit export (all four models
# below converge and print AIC/BIC) - but that data is fabricated to be
# well-behaved (evenly spread ages, no duplicate timepoints, plenty of
# observations per child). It says nothing about whether YOUR real data
# converges. Run `growth_model_coverage_report` first and check its output
# - especially the duplicate-timepoint and observations-per-child sections -
# against your own data before trusting this on it.
#
# Requires nlme specifically (not lme4): lme4 has no continuous-time AR
# correlation structure, and statsmodels.MixedLM (Python) has no residual
# correlation structures at all. corCAR1() is why this is an R script.

library(nlme) # ships with base R; the only hard dependency this script needs

# ---------------------------------------------------------------------------
# 0. Load and sanity-check. Run `python manage.py growth_model_coverage_report`
#    BEFORE this script and compare its numbers to what's printed here.
# ---------------------------------------------------------------------------

# CSV needs no extra package (base R read.csv). For a large export, install
# arrow and use `arrow::read_parquet(csv_path)` instead - same column names
# either way, everything below is unaffected by the choice.
#
# Path comes from the command line so this can be scripted:
#   Rscript analysis/growth_splines.R exports/longform_20260101_120000.csv
# or see scripts/demo_growth_splines.sh, which finds the latest export for you.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop(
    "Usage: Rscript analysis/growth_splines.R <path-to-longform-export.csv>\n",
    "Generate one with: python manage.py export_longform --format csv\n",
    "Or just run: scripts/demo_growth_splines.sh"
  )
}
csv_path <- args[1]
if (!file.exists(csv_path)) {
  stop("Export file not found: ", csv_path)
}
df <- read.csv(csv_path)

df <- df[!is.na(df$height) & !is.na(df$age_months), ]

# corCAR1 hard-errors on duplicate (id, time) pairs within a group. The app
# has no DB constraint preventing two visits on the same day for the same
# patient, so check and collapse before fitting - don't skip this.
dupes <- df[duplicated(df[, c("patient_id", "age_months")]) |
  duplicated(df[, c("patient_id", "age_months")], fromLast = TRUE), ]
if (nrow(dupes) > 0) {
  message(nrow(dupes), " duplicate-timepoint rows found - averaging within (patient_id, age_months).")
  df <- aggregate(
    cbind(height, weight) ~ patient_id + age_months + gender,
    data = df, FUN = mean
  )
}

df <- df[order(df$patient_id, df$age_months), ]

# ---------------------------------------------------------------------------
# 1. Spline knots: placed at quantiles of the OBSERVED age distribution, not
#    copied from the paper (3, 6, 18, 24, 40 assumes dense birth-cohort data;
#    a knot beyond your data's age range makes that basis column collinear
#    with age^3 and lme() will misbehave or fail to converge). Adjust K.
# ---------------------------------------------------------------------------

K <- 5 # number of interior knots; drop to 3 if the coverage report showed thin data
knots <- quantile(df$age_months, probs = seq(1, K) / (K + 1), na.rm = TRUE)
message("Knots (months): ", paste(round(knots, 1), collapse = ", "))

t <- df$age_months
t2 <- t^2
t3 <- t^3
spline_terms <- sapply(knots, function(k) pmax(t - k, 0)^3)
colnames(spline_terms) <- paste0("t3_k", seq_along(knots))
df <- cbind(df, spline_terms)
spline_formula_terms <- paste(colnames(spline_terms), collapse = " + ")

is_female <- df$gender == "F"

# The paper's I(t > 24) proxy for recumbent-vs-standing measurement. Compare
# this to the real `standing_or_upright` field (growth_model_coverage_report
# reports the agreement rate) - if they're near-identical, either works; if
# not, prefer the real per-visit flag over the age-based proxy.
over_24 <- df$age_months > 24

# ---------------------------------------------------------------------------
# 2. Stepwise model building, exactly as the paper stages it. Fit each step
#    and look at AIC/BIC and residual diagnostics before moving to the next -
#    don't jump straight to the final model.
# ---------------------------------------------------------------------------

base_formula <- as.formula(paste(
  "height ~ is_female + over_24 + t + t2 + t3 +", spline_formula_terms
))

# Step 1: OLS, no mixed effects. Baseline only - not appropriate for
# subject-specific prediction, but useful to see how much the later steps buy you.
fit_ols <- lm(base_formula, data = df)
cat("OLS AIC/BIC:", AIC(fit_ols), BIC(fit_ols), "\n")

# Step 2: random intercept only.
fit_ri <- lme(base_formula,
  random = ~ 1 | patient_id, data = df, method = "REML"
)
cat("Random-intercept AIC/BIC:", AIC(fit_ri), BIC(fit_ri), "\n")

# Step 3: random intercept + random slope on linear age term (matches the
# paper - only t gets a random slope, not t2/t3/the spline terms).
fit_ris <- lme(base_formula,
  random = ~ 1 + t | patient_id, data = df, method = "REML"
)
cat("Random-slope AIC/BIC:", AIC(fit_ris), BIC(fit_ris), "\n")

# Step 4: + CAR(1) residual correlation for irregularly-spaced repeated
# measurements. This is the step most likely to have convergence trouble on
# jornada-style sparse data - if it fails, stop here and report step 3.
fit_car1 <- lme(base_formula,
  random = ~ 1 + t | patient_id,
  correlation = corCAR1(form = ~ t | patient_id),
  data = df, method = "REML"
)
cat("Random-slope + CAR(1) AIC/BIC:", AIC(fit_car1), BIC(fit_car1), "\n")

# ---------------------------------------------------------------------------
# 3. Extending beyond the paper: household/environment covariates and
#    family-level nesting.
#
# The paper's cohort recruited one child per household, so family nesting
# was structurally absent from their model. This project tracks multiple
# children per family - growth_model_coverage_report's "Family nesting"
# section tells you whether that's common enough here to matter.
#
# Household/environment variables are just additional fixed effects (the
# X_i*gamma term in the paper's model) - add them to `base_formula` above,
# e.g. `+ household_income_proxy + dietary_diversity_score`. If you add
# family-level nesting, corCAR1's `form` must match the new grouping, e.g.:
#   random = ~ 1 + t | family_id/patient_id
#   correlation = corCAR1(form = ~ t | family_id/patient_id)
# Expect this to be harder to converge than the patient-only model - add it
# only after step 4 above fits cleanly.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 4. Growth velocity (first derivative) for the final chosen model, e.g. fit_car1.
#    p * sum_l (beta_l + b_il) * t^(l-1) + p * sum_k b_k * (t - knot_k)_+^(p-1)
#    For a subject `su`, extract fitted coefficients and evaluate on a grid -
#    see the paper's Additional file 1 for the plotting pattern this follows.
# ---------------------------------------------------------------------------
