"""
DGA binary LightGBM classifier for DomainRadar

Classifies malware domains using the Light Gradient-Boosting Machine (LightGBM) model.
"""
__author__ = "Radek Hranicky"

import os
import shap
import joblib
import numpy as np
import pandas as pd
from pandas import DataFrame
from pandas.core.dtypes import common as com

from classifiers.options import PipelineOptions


class Clf_dga_binary_lgbm:
    """
        Class for the LightGBM DGA binary (DGA/non-DGA) classifier.
        Expects the model loaded in the ./models/ directory.
        Use the `classify` method to classify a dataset of domain names.
    """

    def __init__(self, options: PipelineOptions):
        """
        Initializes the classifier.
        """

        # Load the LightGBM model
        self.model = joblib.load(os.path.join(options.models_dir, 'dga_binary_lgbm_model.joblib'))

        # Initialize SHAP explainer
        self.explainer = shap.TreeExplainer(self.model)

        # Get the number of features expected by the model
        self.expected_feature_size = self.model.n_features_

        # Columns that are not used in the model
        self.disqualified_columns = ["tls_joint_isoitu_policy_crt_count", "rdap_time_from_last_change", "lex_www_flag"]

    def cast_timestamp(self, df: DataFrame):
        """
        Cast timestamp fields to seconds since epoch.
        """
        for col in df.columns:
            if com.is_timedelta64_dtype(df[col]):
                df[col] = df[col].dt.total_seconds()  # This converts timedelta to float (seconds)
            elif com.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].astype(np.int64) // 10 ** 9  # Converts datetime64 to Unix timestamp (seconds)

        return df


    

    def debug_domain(self, domain_name: str, feature_vectors: DataFrame, n_top_features: int = 10):
        """
        Debug a specific domain by calculating the feature importance for its classification.
        
        Args:
            domain_name (str): The domain name to debug.
            input_data (DataFrame): The feature vector of the domain.
            n_top_features (int, optional): Number of top features to display. Default is 10.
        """

        input_data = feature_vectors.copy()

        # Remove disqualified columns
        for column in self.disqualified_columns:
            if column in input_data.columns:
                input_data.drop(column, axis=1, inplace=True)
                
        # Find the row corresponding to the domain name
        domain_row = input_data[input_data['domain_name'] == domain_name]
        if domain_row.empty:
            raise ValueError("Domain name not found in the input data.")

        # Drop the 'domain_name' and 'label' columns if they exist
        domain_row = domain_row.drop(['domain_name', 'label'], axis=1, errors='ignore')

        # Cast timestamps
        domain_row = self.cast_timestamp(domain_row)

        # Handle NaNs
        domain_row.fillna(-1, inplace=True)

        # Calculate SHAP values for the domain
        shap_values = self.explainer.shap_values(domain_row)

        # Get the base value (average model output)
        base_value = self.explainer.expected_value

        # Get feature importance for the specific prediction
        domain_shap_values = shap_values[0]  # Since predict_proba is used, shap_values is a list
        domain_feature_importance = zip(domain_row.columns, domain_shap_values)

        # Sort features by absolute SHAP value
        sorted_feature_importance = sorted(domain_feature_importance, key=lambda x: abs(x[1]), reverse=True)

        # Get the top n features
        top_features = sorted_feature_importance[:n_top_features]

        # Store the top features and their values in a dictionary
        feature_info = []
        for feature, importance in top_features:
            feature_info.append({
                "feature": feature,
                "value": domain_row[feature].values[0],
                "shap_value": importance
            })

        # Calculate the probability for the domain
        probability = self.model.predict_proba(domain_row)[:, 1][0]

        # Create data for the force plot
        force_plot_data = (base_value, domain_shap_values, domain_row)

        # Return the information as a dictionary
        return {
            "top_features": feature_info,
            "probability": probability,
            "force_plot_data": force_plot_data
        }


    def classify(self, feature_vectors: DataFrame) -> list:

        input_data = feature_vectors.copy()

        # Remove disqualified columns
        for column in self.disqualified_columns:
            if column in input_data.columns:
                input_data.drop(column, axis=1, inplace=True)

        # Preserve only lex_ columns
        input_data = input_data.filter(regex='^lex_')

        # Drop the 'domain_name' column if it exists
        if 'domain_name' in input_data.columns:
            input_data = input_data.drop('domain_name', axis=1)

        # Drop the 'label' column if it exists
        if 'label' in input_data.columns:
            input_data = input_data.drop('label', axis=1)

        # Cast timestamps
        input_data = self.cast_timestamp(input_data)

        # Handle NaNs
        input_data.fillna(-1, inplace=True)

        # Resolve remining bad values (in case of missing data, etc.)
        def replace_non_numeric(df: pd.DataFrame) -> pd.DataFrame:
            def replace_value(value):
                if isinstance(value, (int, float, bool)):
                    return value
                else:
                    return -1
            return df.applymap(replace_value)
        input_data = replace_non_numeric(input_data)

        # Predict the probabilities of the positive class (malware)
        probabilities = self.model.predict_proba(input_data)[:, 1]

        return probabilities
