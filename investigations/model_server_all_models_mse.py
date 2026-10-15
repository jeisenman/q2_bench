# Databricks notebook source
# MAGIC %md
# MAGIC # Fit and compare Model Server models
# MAGIC
# MAGIC Fits all six migration models on deterministic training splits and
# MAGIC reports holdout mean squared error (MSE) without writing remote data.
# COMMAND ----------
# MAGIC %pip install --no-deps scikit-learn==1.9.1 narwhals
# COMMAND ----------
# MAGIC %pip install --no-deps /dbfs/FileStore/jordan.eisenman/dimodels/dimodels-2.4.0-py3-none-any.whl
# COMMAND ----------
dbutils.library.restartPython()
# COMMAND ----------
# MAGIC %md
# MAGIC ## Get short-lived Model Server tokens
# MAGIC
# MAGIC Run these in a **local terminal**, not Databricks. The helper opens a
# MAGIC browser and receives its callback on localhost. Install
# MAGIC `../di-model-server/di-models` first if `dms-token` is unavailable.
# MAGIC
# MAGIC ```bash
# MAGIC dms-token alpha
# MAGIC dms-token staging
# MAGIC dms-token prod
# MAGIC ```
# MAGIC
# MAGIC Do not save the returned tokens in notebook source or output.
# COMMAND ----------
# MAGIC %run "/Shared/Packages/Connect-to-DataMart-ADLS-Gen2/"
# COMMAND ----------
import sys
from collections.abc import Callable
from typing import Any
import numpy as np
import pandas as pd
import sklearn
from dimodels.contract import BaseModel, PredictionInput, PredictionOutput
from dimodels.generate import PerturbedLine
from dimodels.models.construction_draw import (
    ConstructionDrawPredictor,
    FEATURE_ORDER as CONSTRUCTION_FEATURES,
    TARGET_VARIABLE as CONSTRUCTION_TARGET,
)
from dimodels.models.examples.linear_regression import LinReg
from dimodels.models.loc_utilization_no_relationship import (
    FEATURE_ORDER as LOC_NO_FEATURES,
    LOCUtilizationNoRelationshipPredictor,
    TARGET_VARIABLE as LOC_TARGET,
)
from dimodels.models.loc_utilization_with_relationship import (
    FEATURE_ORDER as LOC_WITH_FEATURES,
    LOCUtilizationWithRelationshipPredictor,
)
from dimodels.models.market_spread_distribution import (
    FEATURE_ORDER_V2 as MARKET_FEATURES,
    MarketSpreadDistributionPredictorV2,
    PREDICT_QUANTILES,
    TARGET_VARIABLE as MARKET_TARGET,
)
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split
print(f"Python: {sys.version}")
print(f"scikit-learn: {sklearn.__version__}")
# COMMAND ----------
dbutils.widgets.text("test_fraction", "0.20")
dbutils.widgets.text("random_seed", "123")
dbutils.widgets.text("model_partition", "group-us-01-02")
TEST_FRACTION = float(dbutils.widgets.get("test_fraction"))
RANDOM_SEED = int(dbutils.widgets.get("random_seed"))
MODEL_PARTITION = dbutils.widgets.get("model_partition").strip()
MODELS_URI = "abfss://models-historical@pladls2usdatamartprod.dfs.core.windows.net/"
RESULTS: list[dict[str, Any]] = []
if not 0.0 < TEST_FRACTION < 1.0:
    raise ValueError("test_fraction must be greater than 0 and less than 1")
if not MODEL_PARTITION:
    raise ValueError("model_partition must not be blank")
# COMMAND ----------
def latest_path(dataset: str, version: str, subpath: str) -> str:
    """Find the newest date partition containing the requested training data."""
    root = f"{MODELS_URI}{dataset}/training/VersionPartition={version}/"
    folders = sorted(
        dbutils.fs.ls(root),
        key=lambda item: int(item.name.replace("DatePartition=", "").rstrip("/")),
        reverse=True,
    )
    for folder in folders:
        candidate = f"{folder.path.rstrip('/')}/{subpath.strip('/')}/"
        try:
            if dbutils.fs.ls(candidate):
                return candidate
        except Exception:
            continue
    raise ValueError(f"no usable {subpath} found under {root}")
def regression_arrays(
    frame: pd.DataFrame,
    features: list[str],
    target: str,
    categorical: set[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Validate and clean a regression data set."""
    required = features + [target]
    missing = sorted(set(required).difference(frame.columns))
    if missing:
        raise ValueError(f"training data is missing columns: {missing}")
    cleaned = frame[required].replace(r"^\s*$", np.nan, regex=True).copy()
    for column in [name for name in features if name not in categorical] + [target]:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
    cleaned = cleaned.dropna(subset=required)
    if cleaned.empty:
        raise ValueError("no training rows remain after cleaning")
    for column in categorical:
        cleaned[column] = cleaned[column].astype(str)
    return cleaned[features].to_numpy(dtype=object), cleaned[target].to_numpy()
def evaluate(
    factory: Callable[[], BaseModel],
    features: np.ndarray,
    target: np.ndarray,
    *,
    fit_kwargs: dict[str, Any] | None = None,
    prediction_column: int | None = None,
    loss_output: str = "prediction",
) -> BaseModel:
    """Fit one deterministic split and report holdout MSE."""
    kwargs = fit_kwargs or {}
    x_train, x_test, y_train, y_test = train_test_split(
        features, target, test_size=TEST_FRACTION, random_state=RANDOM_SEED
    )
    candidate = factory()
    candidate.fit(x_train, y_train, **kwargs)
    output = candidate.predict(
        PredictionInput(candidate.name, candidate.model_partition, x_test.tolist())
    )
    if output.error:
        raise RuntimeError(f"{candidate.name} prediction failed: {output.error}")
    predictions = np.asarray(output.prediction, dtype=float)
    predictions = (
        predictions.reshape(-1)
        if prediction_column is None
        else predictions[:, prediction_column]
    )
    mse = float(mean_squared_error(y_test, predictions))
    result = {
        "model": candidate.name,
        "available_rows": len(target),
        "training_rows": len(y_train),
        "holdout_rows": len(y_test),
        "loss_output": loss_output,
        "mse": mse,
        "rmse": float(np.sqrt(mse)),
    }
    RESULTS.append(result)
    display(pd.DataFrame([result]))
    return candidate
# COMMAND ----------
# MAGIC %md
# MAGIC ## MarketSpreadDistributionPredictorV2
# MAGIC MSE uses p50 because a distribution model needs one point estimate per row.
# COMMAND ----------
market_path = latest_path("market_spread_distribution", "v1.2", "dataset")
market_x, market_y = regression_arrays(
    spark.read.csv(market_path, header=True).toPandas(),
    list(MARKET_FEATURES),
    MARKET_TARGET,
    {"ProductBin", "RateType", "IndexFamily"},
)
P50_COLUMN = list(PREDICT_QUANTILES).index(0.5)
print(f"Training path: {market_path}")
market_v2 = evaluate(
    lambda: MarketSpreadDistributionPredictorV2(MODEL_PARTITION),
    market_x,
    market_y,
    prediction_column=P50_COLUMN,
    loss_output="p50",
)
# COMMAND ----------
# MAGIC %md
# MAGIC ## ConstructionDrawPredictor
# COMMAND ----------
construction_path = latest_path("construction_draw", "v3.0", "dataset")
construction_x, construction_y = regression_arrays(
    spark.read.parquet(construction_path).toPandas(),
    list(CONSTRUCTION_FEATURES),
    CONSTRUCTION_TARGET,
    set(),
)
print(f"Training path: {construction_path}")
construction = evaluate(
    lambda: ConstructionDrawPredictor(MODEL_PARTITION),
    construction_x,
    construction_y,
    fit_kwargs={"params": {}},
)
# COMMAND ----------
# MAGIC %md
# MAGIC ## LOCUtilizationNoRelationshipPredictor
# COMMAND ----------
loc_no_path = latest_path("loc_utilization", "v1.1", "data_no_relationship")
loc_no_x, loc_no_y = regression_arrays(
    spark.read.csv(loc_no_path, header=True).toPandas(),
    list(LOC_NO_FEATURES),
    LOC_TARGET,
    {"LoanClientId", "LoanRateType", "LoanPaymentFrequency"},
)
print(f"Training path: {loc_no_path}")
loc_no = evaluate(
    lambda: LOCUtilizationNoRelationshipPredictor(MODEL_PARTITION),
    loc_no_x,
    loc_no_y,
)
# COMMAND ----------
# MAGIC %md
# MAGIC ## LOCUtilizationWithRelationshipPredictor
# COMMAND ----------
loc_with_path = latest_path("loc_utilization", "v1.1", "data_with_relationship")
loc_with_x, loc_with_y = regression_arrays(
    spark.read.csv(loc_with_path, header=True).toPandas(),
    list(LOC_WITH_FEATURES),
    LOC_TARGET,
    {
        "LoanClientId",
        "LoanRateType",
        "LoanPaymentFrequency",
        "RelationshipNaics4Mode",
        "RelationshipZip3Mode",
    },
)
print(f"Training path: {loc_with_path}")
loc_with = evaluate(
    lambda: LOCUtilizationWithRelationshipPredictor(MODEL_PARTITION),
    loc_with_x,
    loc_with_y,
)
# COMMAND ----------
# MAGIC %md
# MAGIC ## LinReg
# COMMAND ----------
np.random.seed(RANDOM_SEED)
linreg_frame, linreg_target = PerturbedLine().generate(1000)
linreg = evaluate(
    lambda: LinReg("canary-test"),
    linreg_frame.to_numpy(dtype=float),
    linreg_target.to_numpy(dtype=float),
)
# COMMAND ----------
# MAGIC %md
# MAGIC ## MarketSpreadDistributionPredictorV3
# MAGIC This compatibility cell preserves the existing V3 model under sklearn 1.9.
# COMMAND ----------
import dimodels.models.market_spread_distribution as market_module
from scipy import stats
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, PowerTransformer, QuantileTransformer
class OrdinalUnknownEncoder(OrdinalEncoder):
    def __init__(self, categories="auto", unknown_values=None, dtype=np.float64):
        self.categories = categories
        self.unknown_values = [] if unknown_values is None else unknown_values
        self.dtype = dtype
    def fit(self, features, target=None):
        self._fit(features, handle_unknown="use_values")
        return self
    def transform(self, features):
        if features.shape[1] != len(self.unknown_values):
            raise ValueError("unknown_values must contain one value per feature")
        encoded, mask = self._transform(features, handle_unknown="use_values")
        transformed = encoded.astype(self.dtype, copy=False)
        for column, unknown_value in enumerate(self.unknown_values):
            transformed[~mask[:, column], column] = unknown_value
        return transformed
    def fit_transform(self, features, target=None, **fit_params):
        return self.fit(features, target).transform(features)
class DistributionPredictor(RegressorMixin, BaseEstimator):
    def __init__(
        self,
        mean_model=None,
        error_model=None,
        y_transform=None,
        output="mean_std",
        error_train_size=0.33,
        std_warning_cutoff=0.975,
    ):
        self.mean_model, self.error_model = mean_model, error_model
        self.y_transform, self.output = y_transform, output
        self.error_train_size = error_train_size
        self.std_warning_cutoff = std_warning_cutoff
    def fit(self, features, target):
        params = market_module.GBM_PARAMS
        self.mean_model = self.mean_model or GradientBoostingRegressor(**params)
        self.error_model = self.error_model or GradientBoostingRegressor(**params)
        if self.y_transform:
            target = self.y_transform.fit_transform(target.reshape(-1, 1)).ravel()
        x_mean, x_error, y_mean, y_error = train_test_split(
            features, target, random_state=0, test_size=self.error_train_size
        )
        self.mean_model.fit(x_mean, y_mean)
        self.error_model.fit(
            x_error, (y_error - self.mean_model.predict(x_error)) ** 2
        )
        deviations = np.abs(self.error_model.predict(x_mean)) ** 0.5
        self.std_warning_value = np.quantile(deviations, self.std_warning_cutoff)
        self.mean_model.fit(features, target)
        return self
    def predict(self, features):
        mean = np.reshape(self.mean_model.predict(features), (-1, 1))
        deviation = np.reshape(
            np.abs(self.error_model.predict(features)) ** 0.5, (-1, 1)
        )
        warning = np.reshape(deviation > self.std_warning_value, (-1, 1))
        values = mean + np.reshape(stats.norm().ppf(self.output), (1, -1)) * deviation
        if self.y_transform:
            limit = market_module.get_power_transform_limit(self.y_transform)
            if limit:
                if limit < 0:
                    values[values <= limit] = limit * 1.001
                else:
                    values[values >= limit] = limit * 0.999
            for column in range(values.shape[1]):
                values[:, column] = self.y_transform.inverse_transform(
                    values[:, column].reshape(-1, 1)
                ).ravel()
        return np.concatenate([values, warning], axis=1)
class MarketSpreadDistributionPredictorV3(BaseModel):
    name, environment = "MarketSpreadDistributionPredictorV3", "scikit-learn"
    def fit(self, features, target):
        transforms = ColumnTransformer(
            [
                ("categories", OrdinalEncoder(categories=[
                    market_module.PRODUCT_BIN_CATEGORIES,
                    market_module.RATE_TYPE_CATEGORIES,
                ]), [0, 1]),
                ("index_family", OrdinalUnknownEncoder(
                    categories=[market_module.INDEX_FAMILY_CATEGORIES],
                    unknown_values=[market_module.INDEX_FAMILY_UNKNOWN_VALUE],
                ), [2]),
                ("numeric", QuantileTransformer(output_distribution="normal"), [3, 4, 5, 6]),
            ]
        )
        self.feature_warning_values = market_module.calculate_feature_warning_cutoffs(
            features, 0.01, (3, 4, 5)
        )
        self._model = Pipeline([
            ("transform", transforms),
            ("model", DistributionPredictor(
                output=PREDICT_QUANTILES,
                y_transform=PowerTransformer(method="yeo-johnson"),
            )),
        ]).fit(features, target)
        return self
    def predict(self, data: PredictionInput) -> PredictionOutput:
        if self.model is None:
            return PredictionOutput(error="model has not been fit")
        features = np.array(data.data, ndmin=2, dtype=object)
        prediction = self.model.predict(features)
        warnings = market_module.determine_feature_based_warnings(
            features, self.feature_warning_values
        )
        prediction[:, -1] = np.maximum(prediction[:, -1], warnings)
        return PredictionOutput(prediction.tolist())
for custom_class in (
    OrdinalUnknownEncoder,
    DistributionPredictor,
    MarketSpreadDistributionPredictorV3,
):
    custom_class.__module__ = market_module.__name__
    setattr(market_module, custom_class.__name__, custom_class)
market_v3 = evaluate(
    lambda: MarketSpreadDistributionPredictorV3(MODEL_PARTITION),
    market_x,
    market_y,
    prediction_column=P50_COLUMN,
    loss_output="p50",
)
# COMMAND ----------
# MAGIC %md
# MAGIC ## MSE comparison
# MAGIC MSE values use different target units and should not be ranked across
# MAGIC unrelated models. V2 and V3 are directly comparable because both use p50.
# COMMAND ----------
comparison = pd.DataFrame(RESULTS).sort_values("model")
display(comparison)
print(f"Evaluated {len(comparison)} models")
