# =============================================================================
# Finance, Firms and Jobs in Ghana  -  R translation of python/analysis.py
# World Bank Enterprise Survey, Ghana 2023 (713 formal private establishments)
#
# Author: Evans K. Owusu, PhD
# Translated from the Python pipeline with Claude (AI coding assistant) and
# cross-checked with verify_match.py: both versions must produce the same
# weighted estimates and standard errors.
#
# Usage (from the repo root):
#   Rscript R/analysis.R data/Ghana-2023-full-data.dta
# Writes output/results_r.json (+ R_*.csv tables)
# =============================================================================

pkgs <- c("haven", "survey", "jsonlite")
new <- pkgs[!pkgs %in% rownames(installed.packages())]
if (length(new)) install.packages(new, repos = "https://cloud.r-project.org")
suppressPackageStartupMessages(invisible(lapply(pkgs, library, character.only = TRUE)))

options(survey.lonely.psu = "adjust")      # 12 strata contain a single firm
args <- commandArgs(trailingOnly = TRUE)
path <- if (length(args)) args[1] else "data/Ghana-2023-full-data.dta"
dir.create("output", showWarnings = FALSE)

# ---- 1. Load and clean -------------------------------------------------------
raw <- zap_labels(read_dta(path))

clean  <- function(x) { x <- as.numeric(x); x[!is.na(x) & x < 0] <- NA; x }
yes_no <- function(x) { x <- clean(x); ifelse(x == 1, 1, ifelse(x == 2, 0, NA)) }
recode <- function(x, from, to) { out <- to[match(x, from)]; out }

df <- data.frame(wmedian = as.numeric(raw$wmedian), strata = raw$strata)

l1 <- clean(raw$l1); l2 <- clean(raw$l2)
df$size <- ifelse(is.na(l1), NA, ifelse(l1 <= 19, "Small", ifelse(l1 <= 99, "Medium", "Large")))
df$size_medium <- as.numeric(df$size %in% "Medium")
df$size_large  <- as.numeric(df$size %in% "Large")

df$sector_othmfg  <- as.numeric(raw$a4a == 2)    # ref: food & beverages
df$sector_retail  <- as.numeric(raw$a4a == 3)
df$sector_hotels  <- as.numeric(raw$a4a == 4)
df$sector_othserv <- as.numeric(raw$a4a == 5)
df$region_ashanti  <- as.numeric(raw$a2 == 2)    # ref: Greater Accra, Eastern, Volta, Oti
df$region_western  <- as.numeric(raw$a2 == 3)
df$region_northern <- as.numeric(raw$a2 == 4)

age <- as.numeric(raw$a14y) - clean(raw$b5)
df$firm_age   <- ifelse(age >= 0, age, NA)
df$log_age    <- log1p(df$firm_age)
df$young_firm <- ifelse(is.na(df$firm_age), NA, as.numeric(df$firm_age <= 5))

df$female_mgr <- yes_no(raw$b7a)
df$female_own <- yes_no(raw$b4)
d3b <- clean(raw$d3b); d3c <- clean(raw$d3c)
exp_share <- ifelse(is.na(d3b), 0, d3b) + ifelse(is.na(d3c), 0, d3c)
df$exporter <- ifelse(is.na(d3b) & is.na(d3c), NA, as.numeric(exp_share >= 10))
df$audited  <- yes_no(raw$k21)
df$website  <- yes_no(raw$c22b)
h1 <- yes_no(raw$h1); h5 <- yes_no(raw$h5)
df$innovator <- ifelse(is.na(h1) & is.na(h5), NA,
                       as.numeric((h1 %in% 1) | (h5 %in% 1)))

k30 <- clean(raw$k30)
df$finance_major <- ifelse(is.na(k30), NA, as.numeric(k30 >= 3))
obstacle_labels <- c("Access to finance", "Access to land", "Licensing & permits", "Corruption",
                     "Courts", "Crime & theft", "Customs & trade", "Electricity", "Skills shortage",
                     "Labour regulations", "Political instability", "Informal competitors",
                     "Tax administration", "Tax rates", "Transport")
df$biggest_obstacle <- recode(clean(raw$m1a), 1:15, obstacle_labels)
df$finance_top <- ifelse(is.na(df$biggest_obstacle), NA, as.numeric(df$biggest_obstacle == "Access to finance"))

df$has_account <- yes_no(raw$k6)
df$has_credit  <- recode(clean(raw$k82),  1:4, c(1, 1, 1, 0))
df$applied     <- recode(clean(raw$k162), 1:4, c(1, 1, 1, 0))
k17 <- clean(raw$k17)
reason_labels <- c("No need (enough capital)", "Complex procedures", "Unfavourable interest rates",
                   "Collateral too high", "Loan size/maturity too small", "Did not expect approval", "Other")
df$reason_not_applying <- recode(k17, 1:7, reason_labels)

df$needs_credit <- ifelse(df$applied %in% 1, 1,
                   ifelse(df$applied %in% 0 & k17 %in% 2:7, 1,
                   ifelse(df$applied %in% 0 & k17 %in% 1, 0, NA)))
df$discouraged <- ifelse(df$needs_credit %in% 1, 1 - df$applied, NA)

approved <- recode(clean(raw$k20a1), 1:4, c(1, 1, 0, 0))
df$applied_approved <- ifelse(df$applied %in% 0, 0,
                       ifelse(df$applied %in% 1 & !is.na(approved), approved, NA))
df$approved_if_applied <- ifelse(df$applied %in% 1, approved, NA)

df$outages   <- yes_no(raw$c6)
df$generator <- yes_no(raw$c10)

ok <- !is.na(l1) & !is.na(l2) & (l1 + l2) > 0
df$emp_growth <- ifelse(ok, (l1 - l2) / ((l1 + l2) / 2) / 3 * 100, NA)
df$base_size_medium <- ifelse(is.na(l2), NA, as.numeric(l2 >= 20 & l2 < 100))
df$base_size_large  <- ifelse(is.na(l2), NA, as.numeric(l2 >= 100))

# ---- 2. Survey design --------------------------------------------------------
des <- svydesign(ids = ~1, strata = ~strata, weights = ~wmedian, data = df)
res <- list()

wmean <- function(var, design = des) {
  est <- svymean(as.formula(paste0("~", var)), design, na.rm = TRUE)
  c(est = unname(coef(est)), se = unname(SE(est)))
}

# ---- 3. Headline indicators --------------------------------------------------
headline <- c(finance_biggest_obstacle = "finance_top", finance_major_obstacle = "finance_major",
              has_account = "has_account", needs_credit = "needs_credit", applied = "applied",
              applied_and_approved = "applied_approved", has_credit = "has_credit",
              discouraged_of_needing = "discouraged", approved_if_applied = "approved_if_applied",
              outages = "outages", generator = "generator", female_top_manager = "female_mgr",
              female_ownership = "female_own")
head_tbl <- do.call(rbind, lapply(names(headline), function(k) {
  r <- wmean(headline[[k]])
  res[[paste0("mean.", k)]] <<- r[["est"]]
  res[[paste0("se.", k)]]   <<- r[["se"]]
  data.frame(indicator = k, est = r[["est"]], se = r[["se"]])
}))
write.csv(head_tbl, "output/R_01_headline_indicators.csv", row.names = FALSE)
print(head_tbl, digits = 3)

# ---- 4. Shares of a categorical variable (domain-aware) ----------------------
# Weighted share of each category = svymean of a 0/1 indicator, NA where the
# category is missing; `domain` (logical vector) restricts to a subpopulation
# while keeping the full design (correct domain standard errors).
cat_shares <- function(var, domain = NULL) {
  x <- df[[var]]
  levs <- sort(unique(na.omit(x)))
  sapply(levs, function(l) {
    d <- des
    d$variables$.ind <- ifelse(is.na(x), NA, as.numeric(x == l))
    if (!is.null(domain)) d <- d[domain, ]
    unname(coef(svymean(~.ind, d, na.rm = TRUE))[1])
  })
}
obs <- cat_shares("biggest_obstacle")
for (k in names(obs)) res[[paste0("obstacle.", k)]] <- obs[[k]]
write.csv(data.frame(category = names(obs), est = obs), "output/R_02_biggest_obstacle.csv", row.names = FALSE)

reasons <- cat_shares("reason_not_applying", domain = df$discouraged %in% 1)
for (k in names(reasons)) res[[paste0("reason_disc.", k)]] <- reasons[[k]]

# ---- 5. Gaps by group --------------------------------------------------------
des <- update(des,
  g_size  = size,
  g_mgr   = ifelse(female_mgr == 1, "Female", ifelse(female_mgr == 0, "Male", NA)),
  g_own   = ifelse(female_own == 1, "Any female owner", ifelse(female_own == 0, "No female owner", NA)),
  g_age   = ifelse(young_firm == 1, "Young (0-5 yrs)", ifelse(young_firm == 0, "Established (6+ yrs)", NA)),
  g_cred  = ifelse(has_credit == 1, "Has loan/credit line", ifelse(has_credit == 0, "No loan/credit line", NA)))
groupings <- c("Firm size" = "g_size", "Top manager" = "g_mgr", "Ownership" = "g_own", "Firm age" = "g_age")

for (outcome in c("has_credit", "discouraged", "finance_major", "applied")) {
  for (gname in names(groupings)) {
    gv <- groupings[[gname]]
    d  <- des[!is.na(des$variables[[gv]]), ]
    t  <- svyby(as.formula(paste0("~", outcome)), as.formula(paste0("~", gv)), d, svymean, na.rm = TRUE)
    for (i in seq_len(nrow(t))) res[[paste0("by.", outcome, ".", gname, ".", t[[gv]][i])]] <- t[[outcome]][i]
  }
}

# ---- 6. Models ---------------------------------------------------------------
fe <- "sector_othmfg + sector_retail + sector_hotels + sector_othserv + region_ashanti + region_western + region_northern"

m1 <- svyglm(as.formula(paste("has_credit ~ size_medium + size_large +", fe,
                              "+ female_mgr + young_firm + exporter + audited + website + innovator")),
             design = des, family = quasibinomial())
m2 <- svyglm(as.formula(paste("emp_growth ~ has_credit + base_size_medium + base_size_large +", fe,
                              "+ female_mgr + exporter + log_age")),
             design = des, family = gaussian())

for (nm in c("m1", "m2")) {
  m <- get(nm)
  cf <- coef(m); se <- sqrt(diag(vcov(m)))
  for (t in names(cf)) {
    res[[paste0(nm, ".coef.", t)]] <- unname(cf[t])
    res[[paste0(nm, ".se.", t)]]   <- unname(se[t])
  }
  res[[paste0(nm, ".n")]] <- length(m$y)
  tbl <- data.frame(term = names(cf), estimate = cf, se = se, row.names = NULL)
  if (nm == "m1") tbl$odds_ratio <- exp(tbl$estimate)
  write.csv(tbl, paste0("output/R_", nm, ".csv"), row.names = FALSE)
}
print(summary(m1)); print(summary(m2))

res[["mean.emp_growth"]] <- wmean("emp_growth")[["est"]]
eg <- svyby(~emp_growth, ~g_cred, des[!is.na(des$variables$g_cred), ], svymean, na.rm = TRUE)
for (i in seq_len(nrow(eg))) res[[paste0("emp_growth.", eg$g_cred[i])]] <- eg$emp_growth[i]

write_json(res, "output/results_r.json", auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("\nDone. Wrote output/results_r.json\n")
