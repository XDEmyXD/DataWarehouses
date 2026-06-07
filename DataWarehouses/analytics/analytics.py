from datetime import datetime, timezone

from db.database import db, timeseries_collection

try:
    from pyspark.ml.feature import VectorAssembler
    from pyspark.ml.regression import LinearRegression
    from pyspark.sql import SparkSession
    from pyspark.sql.functions import col, expr, substring, avg, min as spark_min, max as spark_max, count as spark_count
    HAS_PYSPARK = True
except Exception:
    VectorAssembler = None
    LinearRegression = None
    SparkSession = None
    col = expr = substring = avg = spark_min = spark_max = spark_count = None
    HAS_PYSPARK = False

# Fallback using pandas + scikit-learn when PySpark is not available or fails
try:
    import pandas as pd
    import numpy as np
    from sklearn.linear_model import LinearRegression as SKLinearRegression
    HAS_PANDAS = True
except Exception:
    pd = None
    np = None
    SKLinearRegression = None
    HAS_PANDAS = False


def _get_spark_session():
    if not HAS_PYSPARK:
        raise RuntimeError("PySpark is not installed. Install pyspark to run analytics, or run the app without analytics.")
    return SparkSession.builder.master("local[*]").appName("acme_dw_analytics").getOrCreate()


def _to_local_dicts(df):
    return [row.asDict() for row in df.collect()]


def run_descriptive_analytics():
    """
    [Use Case A] Runs a Spark aggregation over historical time-series data and saves totals.
    """
    # Prefer PySpark if available
    if HAS_PYSPARK:
        try:
            print("Running descriptive analytics (PySpark)...")
            records = list(timeseries_collection.find({}, {"_id": 0, "asset_id": 1, "business_date": 1, "metrics": 1}))
            if not records:
                print("No time-series records found for descriptive analytics.")
                return []

            spark = _get_spark_session()
            df = spark.createDataFrame(records).withColumn(
                "business_date_year", substring(col("business_date"), 1, 4).cast("int")
            ).withColumn("close", col("metrics")["close"].cast("double"))

            aggregated = (
                df.groupBy("asset_id", "business_date_year")
                .agg(
                    spark_count("*").alias("record_count"),
                    spark_min("close").alias("min_close_price"),
                    spark_max("close").alias("max_close_price"),
                    avg("close").alias("average_close_price"),
                )
                .orderBy("asset_id", "business_date_year")
            )

            totals_collection = db["totals"]
            totals_collection.drop()
            inserted_summaries = []

            for summary in _to_local_dicts(aggregated):
                summary["average_close_price"] = round(summary["average_close_price"], 2)
                totals_collection.insert_one(summary)
                inserted_summaries.append(summary)
                print(
                    f"Saved yearly summary for {summary['asset_id']} year {summary['business_date_year']} ({summary['record_count']} records)"
                )

            print("Descriptive analytics finished.")
            spark.stop()
            return inserted_summaries
        except Exception as e:
            print(f"PySpark descriptive analytics failed: {e}. Falling back to pandas if available.")

    # Pandas fallback
    if HAS_PANDAS:
        print("Running descriptive analytics (pandas)...")
        records = list(timeseries_collection.find({}, {"_id": 0, "asset_id": 1, "business_date": 1, "metrics": 1}))
        if not records:
            print("No time-series records found for descriptive analytics.")
            return []

        rows = []
        for r in records:
            metrics = r.get("metrics") or {}
            # prefer 'close_price' then 'close'
            close_val = metrics.get("close_price") if isinstance(metrics, dict) else None
            if close_val is None:
                close_val = metrics.get("close") if isinstance(metrics, dict) else None
            if close_val is None:
                continue
            try:
                year = int(str(r.get("business_date", ""))[:4])
            except Exception:
                continue
            rows.append({"asset_id": r.get("asset_id"), "business_date_year": year, "close": float(close_val)})

        if not rows:
            print("No usable close-price records for descriptive analytics.")
            return []

        df = pd.DataFrame(rows)
        grouped = df.groupby(["asset_id", "business_date_year"]).agg(
            record_count=("close", "count"),
            min_close_price=("close", "min"),
            max_close_price=("close", "max"),
            average_close_price=("close", "mean"),
        ).reset_index()

        totals_collection = db["totals"]
        totals_collection.drop()
        inserted_summaries = []
        for _, row in grouped.iterrows():
            summary = {
                "asset_id": row["asset_id"],
                "business_date_year": int(row["business_date_year"]),
                "record_count": int(row["record_count"]),
                "min_close_price": float(row["min_close_price"]),
                "max_close_price": float(row["max_close_price"]),
                "average_close_price": round(float(row["average_close_price"]), 2),
            }
            totals_collection.insert_one(summary)
            inserted_summaries.append(summary)
            print(f"Saved yearly summary for {summary['asset_id']} year {summary['business_date_year']} ({summary['record_count']} records)")

        print("Descriptive analytics finished (pandas).")
        return inserted_summaries

    print("No analytics engine available (PySpark or pandas). Skipping descriptive analytics.")
    return []


def run_predictive_analytics():
    """
    [Use Case B] Runs Spark ML linear regression on asset close-price history and saves predictions.
    """
    # Prefer PySpark when available
    if HAS_PYSPARK:
        try:
            print("Running predictive analytics (PySpark)...")
            asset_ids = timeseries_collection.distinct("asset_id")
            regression_results = db["regression_results"]
            regression_results.drop()

            if not asset_ids:
                print("No assets found for predictive analytics.")
                return []

            spark = _get_spark_session()

            inserted_predictions = []
            for asset_id in asset_ids:
                records = list(timeseries_collection.find({"asset_id": asset_id}, {"_id": 0, "business_date": 1, "metrics": 1}).sort("business_date", 1))
                prices = [record.get("metrics", {}).get("close") or record.get("metrics", {}).get("close_price") for record in records if (record.get("metrics", {}).get("close") is not None) or (record.get("metrics", {}).get("close_price") is not None)]
                if len(prices) < 3:
                    print(f" Skipping {asset_id}: not enough records for a regression model.")
                    continue

                training_data = [
                    {"timestep": float(index), "close": float(price), "business_date": record["business_date"]}
                    for index, (record, price) in enumerate(zip(records, prices))
                ]

                df = spark.createDataFrame(training_data)
                assembler = VectorAssembler(inputCols=["timestep"], outputCol="features")
                train_df = assembler.transform(df).select("features", "close")

                lr = LinearRegression(featuresCol="features", labelCol="close", maxIter=50, regParam=0.1)
                model = lr.fit(train_df)
                next_timestep = float(len(training_data))

                predicted_price = float(model.predict([next_timestep]))
                r_squared = float(model.summary.r2)

                prediction_doc = {
                    "asset_id": asset_id,
                    "calculation_time": datetime.now(timezone.utc).isoformat(),
                    "training_points": len(training_data),
                    "last_known_close": prices[-1],
                    "calculated_trend_slope": round(float(model.coefficients[0]), 6),
                    "intercept": round(float(model.intercept), 2),
                    "predicted_next_close_price": round(predicted_price, 2),
                    "r_squared": round(r_squared, 4),
                    "last_business_date": records[-1]["business_date"],
                }
                regression_results.insert_one(prediction_doc)
                inserted_predictions.append(prediction_doc)
                print(
                    f"Created prediction for {asset_id}: last close {prices[-1]} predicted next close {predicted_price}"
                )

            print("Predictive analytics finished.")
            spark.stop()
            return inserted_predictions
        except Exception as e:
            print(f"PySpark predictive analytics failed: {e}. Falling back to pandas/sklearn if available.")

    # Pandas + sklearn fallback
    if HAS_PANDAS and SKLinearRegression:
        print("Running predictive analytics (pandas + sklearn)...")
        asset_ids = list(timeseries_collection.distinct("asset_id"))
        regression_results = db["regression_results"]
        regression_results.drop()

        if not asset_ids:
            print("No assets found for predictive analytics.")
            return []

        inserted_predictions = []
        for asset_id in asset_ids:
            records = list(timeseries_collection.find({"asset_id": asset_id}, {"_id": 0, "business_date": 1, "metrics": 1}).sort("business_date", 1))
            prices = [ (rec.get("metrics", {}).get("close") if rec.get("metrics", {}).get("close") is not None else rec.get("metrics", {}).get("close_price")) for rec in records if rec.get("metrics") ]
            prices = [float(p) for p in prices if p is not None]
            if len(prices) < 3:
                print(f" Skipping {asset_id}: not enough records for a regression model.")
                continue

            X = np.arange(len(prices)).reshape(-1, 1)
            y = np.array(prices)
            model = SKLinearRegression()
            model.fit(X, y)
            next_timestep = np.array([[len(prices)]])
            predicted_price = float(model.predict(next_timestep)[0])
            r_squared = float(model.score(X, y))

            prediction_doc = {
                "asset_id": asset_id,
                "calculation_time": datetime.now(timezone.utc).isoformat(),
                "training_points": len(prices),
                "last_known_close": prices[-1],
                "calculated_trend_slope": round(float(model.coef_[0]), 6),
                "intercept": round(float(model.intercept_), 2),
                "predicted_next_close_price": round(predicted_price, 2),
                "r_squared": round(r_squared, 4),
                "last_business_date": records[-1]["business_date"],
            }
            regression_results.insert_one(prediction_doc)
            inserted_predictions.append(prediction_doc)
            print(f"Created prediction for {asset_id}: last close {prices[-1]} predicted next close {predicted_price}")

        print("Predictive analytics finished (pandas + sklearn).")
        return inserted_predictions

    print("No analytics engine available (PySpark or pandas/sklearn). Skipping predictive analytics.")
    return []


if __name__ == "__main__":
    run_descriptive_analytics()
    run_predictive_analytics()