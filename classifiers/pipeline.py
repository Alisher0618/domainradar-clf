import datetime
import importlib.util
import pandas as pd
import warnings
import joblib

from .options import PipelineOptions
from .preprocessor import Preprocessor
from .feature_definition import features_in_expected_order

#from .Clf_phishing_cnn import Clf_phishing_cnn
#from .Clf_phishing_deepnn import Clf_phishing_deepnn
from .Clf_phishing_lgbm import Clf_phishing_lgbm
from .Clf_phishing_xgboost import Clf_phishing_xgboost
from .Clf_phishing_dns_nn import Clf_phishing_dns_nn
from .Clf_phishing_rdap_nn import Clf_phishing_rdap_nn
#from .Clf_phishing_ip_nn import Clf_phishing_ip_nn
from .Clf_phishing_html_lgbm import Clf_phishing_html_lgbm
from .Clf_malware_lgbm import Clf_malware_lgbm
#from .Clf_malware_xgboost import Clf_malware_xgboost
#from .Clf_malware_deepnn import Clf_malware_deepnn

from .Clf_dga_binary_nn import Clf_dga_binary_nn
from .Clf_dga_binary_lgbm import Clf_dga_binary_lgbm
from .Clf_dga_multiclass_lgbm import Clf_dga_multiclass_lgbm
from .Clf_decision_nn import Clf_decision_nn
from .Clf_decision_lgbm import Clf_decision_lgbm
from .Clf_malware_html_lgbm import Clf_malware_html_lgbm


classifier_ids = {
#    "Phishing CNN": 1,
    "Phishing LightGBM": 2,
    "Phishing XGBoost": 3,
#    "Phishing Deep NN": 4,
    "Phishing DNS-based NN": 5,
    "Phishing RDAP-based NN": 6,
#    "Phishing IP-based NN": 8,
    "Phishing HTML-based LightGBM": 19,
    "Malware LightGBM": 10,
#    "Malware XGBoost": 11,
#    "Malware Deep NN": 12,
    "Malware HTML-based LightGBM": 20,
    "DGA Binary NN": 17,
    "DGA Binary LightGBM": 18,
    **{v: k + 100 for (k, v) in Clf_dga_multiclass_lgbm.inverse_class_map.items()}
}

class Pipeline:

    def __init__(self, options: PipelineOptions | None = None):
        """
        Initializes the classification pipeline.
        """

        if options is None:
            options = PipelineOptions()

        # Load classifiers
        #self.clf_phishing_cnn = Clf_phishing_cnn(options)
        #self.clf_phishing_deepnn = Clf_phishing_deepnn(options)
        self.clf_phishing_lgbm = Clf_phishing_lgbm(options)
        self.clf_phishing_xgboost = Clf_phishing_xgboost(options)
        self.clf_phishing_dns_nn = Clf_phishing_dns_nn(options)
        self.clf_phishing_rdap_nn = Clf_phishing_rdap_nn(options)
        #self.clf_phishing_ip_nn = Clf_phishing_ip_nn(options)
        self.clf_phishing_html_lgbm = Clf_phishing_html_lgbm(options)

        self.clf_malware_html_lgbm = Clf_malware_html_lgbm(options)
        self.clf_malware_lgbm = Clf_malware_lgbm(options)
        #self.clf_malware_xgboost = Clf_malware_xgboost(options)
        #self.clf_malware_deepnn = Clf_malware_deepnn(options)

        self.clf_dga_binary_nn = Clf_dga_binary_nn(options)
        self.clf_dga_binary_lgbm = Clf_dga_binary_lgbm(options)
        self.clf_dga_multiclass_lgbm = Clf_dga_multiclass_lgbm(options)
        self.clf_decision_nn = Clf_decision_nn(options)
        self.clf_decision_lgbm = Clf_decision_lgbm(options)

        # Suppress FutureWarning
        warnings.simplefilter(action="ignore", category=FutureWarning)

    def feature_statistics(self, domain_data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates feature statistics for the domain data:
        How many features of each category are available and nonzero.
        """
        # Define the prefixes
        prefixes = ["dns_", "tls_", "ip_", "rdap_", "geo_", "html_"]  # lex_ is always present

        # Initialize a DataFrame with domain names only
        stats = domain_data[["domain_name"]].copy()

        
        # Iterate through each prefix to calculate the required ratios
        for prefix in prefixes:
            # Filter columns with the current prefix
            prefixed_columns = [
                col for col in domain_data.columns if col.startswith(prefix)
            ]

            if prefixed_columns:
                # Calculate the availability ratio (non-NaN and non -1 values)

                stats[f"{prefix}available"] = (
                    domain_data[prefixed_columns]
                    .applymap(lambda x: x != -1 and pd.notna(x))
                    .mean(axis=1)
                )

                # Calculate the nonzero ratio (non-zero values, treating NaN and -1 as zero)
                stats[f"{prefix}nonzero"] = (
                    domain_data[prefixed_columns]
                    .applymap(lambda x: x != 0 and x != -1 and pd.notna(x))
                    .mean(axis=1)
                )
            else:
                # If no columns with the current prefix exist, set ratios to 0
                stats[f"{prefix}available"] = 0
                stats[f"{prefix}nonzero"] = 0
        
        return stats


    def calculate_badness_probability(self, domain_stats: pd.Series) -> float:
        """
        Calculates the badness probability based on the results of invividual classifiers
        and statistical properties of the domain features.
        """

        # Use a copy and ignore columns that are not used
        # in the decision-making model (e.g., html-based classifiers)
        working_stats = domain_stats.copy()


        # Make prediction with the decision-making NN
        badness_probability = self.clf_decision_nn.classify(
            pd.DataFrame([working_stats])
        )[0]

        #badness_probability = self.clf_decision_lgbm.classify(
        #    pd.DataFrame([working_stats])
        #)[0]


        # Heuristics
        if not (
            domain_stats["phishing_avg"] > 0.75 and domain_stats["malware_avg"] > 0.75
        ):
            badness_probability -= 0.1
        elif domain_stats["phishing_avg"] > 0.8 and domain_stats["malware_avg"] > 0.8:
            badness_probability += 0.1

        if not (
            domain_stats["phishing_avg"] > 0.5 and domain_stats["malware_avg"] > 0.5
        ) or (
            domain_stats["malware_avg"] > 0.5 and domain_stats["dga_binary_avg"] > 0.5
        ):
            badness_probability -= 0.1

        if badness_probability < 0.0:
            badness_probability = 0.0
        elif badness_probability > 1.0:
            badness_probability = 1.0

        return badness_probability


    def generate_result(self, stats: pd.Series) -> dict:
        """
        Generated the final classification result for a single domain name
        """

        # Phishing description
        phishing_desc = ""
        if stats["phishing_avg"] < 0.1:
            phishing_desc = "No phishing detected."
        elif 0.1 <= stats["phishing_avg"] < 0.5:
            phishing_desc = "The domain has some similarities to phishing domains."
        elif 0.5 <= stats["phishing_avg"] < 0.9:
            phishing_desc = "The domain has high level of phishing indicators."
        elif stats["phishing_avg"] >= 0.9:
            phishing_desc = "The domain is most certainly a phishing domain."

        # Malware description
        malware_desc = ""
        if stats["malware_avg"] < 0.1:
            malware_desc = "No malware detected."
        elif 0.1 <= stats["malware_avg"] < 0.5:
            malware_desc = "The domain has some similarities to malware domains."
        elif 0.5 <= stats["malware_avg"] < 0.9:
            malware_desc = "The domain has high level of malware indicators."
        elif stats["malware_avg"] >= 0.9:
            malware_desc = "The domain is most certainly a malware domain."

        # DGA description
        dga_desc = ""
        if stats["dga_binary_avg"] < 0.1:
            dga_desc = "No DGA detected."
        elif 0.1 <= stats["dga_binary_avg"] < 0.5:
            dga_desc = "The domain has some similarities to DGA domains."
        elif 0.5 <= stats["dga_binary_avg"] < 0.9:
            dga_desc = "The domain has high level of DGA incidators."
        elif stats["dga_binary_avg"] >= 0.9:
            dga_desc = "The domain is most certainly a DGA domain."

        dga_family_details = dict()

        if stats["dga_binary_avg"] >= 0.5:
            for family_name, family_prob in stats["dga_families"].items():
                dga_family_details[classifier_ids[family_name]] = family_prob

        timestamp_ms = int(datetime.datetime.now(datetime.UTC).timestamp() * 1e3)

        result = {
            "domain_name": stats["domain_name"],
            "aggregate_probability": stats["badness_probability"],
            "aggregate_description": None,
            "timestamp": timestamp_ms,
            "classification_results": [
                {
                    "category": 1,  # Phishing
                    "probability": stats["phishing_avg"],
                    "description": phishing_desc,
                    "details": {
                        #classifier_ids["Phishing CNN"]: stats["phishing_cnn_result"],
                        classifier_ids["Phishing LightGBM"]: stats["phishing_lgbm_result"],
                        classifier_ids["Phishing XGBoost"]: stats["phishing_xgboost_result"],
                        #classifier_ids["Phishing Deep NN"]: stats["phishing_deepnn_result"],
                        classifier_ids["Phishing DNS-based NN"]: stats["phishing_dns_nn_result"],
                        classifier_ids["Phishing RDAP-based NN"]: stats["phishing_rdap_nn_result"],
                        #classifier_ids["Phishing IP-based NN"]: stats["phishing_ip_nn_result"]
                    }
                },
                {
                    "category": 2,  # Malware
                    "probability": stats["malware_avg"],
                    "description": malware_desc,
                    "details": {
                        classifier_ids["Malware LightGBM"]: stats["malware_lgbm_result"],
                        #classifier_ids["Malware XGBoost"]: stats["malware_xgboost_result"],
                        #classifier_ids["Malware Deep NN"]: stats["malware_deepnn_result"],
                    }
                },
                {
                    "category": 3,  # DGA
                    "probability": stats["dga_binary_avg"],
                    "description": dga_desc,
                    "details": {
                        **{
                            classifier_ids["DGA Binary NN"]: stats["dga_binary_deepnn_result"],
                            classifier_ids["DGA Binary LightGBM"]: stats["dga_binary_lgbm_result"],
                        },
                        **dga_family_details,
                    },
                },
            ],
        }

        # Add HTML-based results OR display a message that the HTML-based classifiers are disabled
        if stats["phishing_html_lgbm_result"] != -1:
            result["classification_results"][0]["details"][classifier_ids["Phishing HTML-based LightGBM"]] = stats["phishing_html_lgbm_result"]
        else:
            result["classification_results"][0]["description"] += "\n" + "No HTML code scraped -> HTML-based classifiers disabled."
        
        if stats["malware_html_lgbm_result"] != -1:
            result["classification_results"][1]["details"][classifier_ids["Malware HTML-based LightGBM"]] = stats["malware_html_lgbm_result"]
        else:
            result["classification_results"][1]["description"] += "\n" + "No HTML code scraped -> HTML-based classifiers disabled."

        return result


    def generate_preliminary_results(
        self, df: pd.DataFrame, output_file: str = None, add_final=False
    ) -> pd.DataFrame:
        """
        This method is used to generate preliminary results for training and testing
        the final aggregation model. The parquet contains domain name, label, feature
        statistics and results of individual classifiers.
        Optionally, the results can be saved to a Parquet file. To use this feature, the "arrow" or "dev"
        optional dependency group must be installed (poetry install --with arrow).
        """

        # Calculate the feature statistics
        stats = self.feature_statistics(df)

        # Perform classifications and update stats with their results
        stats = self.run_classifiers(df, stats)

        # Calculte derived staistics (sums, averages, products)
        stats = self.compute_all_derived_stats(stats)

        if add_final:
            # Calculate the overall badness probability
            stats["badness_probability"] = stats.apply(
                self.calculate_badness_probability, axis=1
            )

        # Add the label to the statistics (if present in the input DataFrame)
        # It is used for training the final aggregation model
        if "label" in df.columns:
            stats["label"] = df["label"]

        # If an output file path is provided, save the DataFrame as a Parquet file
        if output_file:
            if importlib.util.find_spec("pyarrow") is None:
                warnings.warn(
                    "The pyarrow library is not installed. Run `poetry install --with dev`."
                )
                return stats

            import pyarrow.parquet as pq
            import pyarrow as pa

            table = pa.Table.from_pandas(stats)
            pq.write_table(table, output_file)

        return stats


    def dump_ndf(
        self, df: pd.DataFrame, classifier_type: str, output_filename=False
    ) -> list[dict]:
        """
        Creates an NDF representation of the input data and stores it as a file.
        """
        if (
            classifier_type != "phishing"
            and classifier_type != "malware"
            and classifier_type != "dga_binary"
            and classifier_type != "dga_multiclass"
        ):
            raise ValueError("Invalid classifier type")

        # Shuffle the feature vector to the order in which it was used in training
        df = df.reindex(columns=features_in_expected_order, copy=False)

        ndf = self.pp.df_to_NDF(df, classifier_type)

        # Store as file if necessary
        if output_filename:
            joblib.dump(ndf, output_filename)

        return ndf


    def debug_domain(self, domain_name: str, df: pd.DataFrame, n_top_features: int = 10):
        """
        Debugs a single domain name by showing the most important features for decision
        """

        df = df.copy()

        # Drop all undesired columns
        df = df[[col for col in df.columns if col in features_in_expected_order]]

        # Rearrange the feature vector to the order in which it was used in training
        df = df.reindex(columns=features_in_expected_order, copy=False)

        ndf_phishing = self.pp.df_to_NDF(df, "phishing")

        return {
            # "phishing_cnn": self.clf_phishing_cnn.debug_domain(domain_name, ndf_phishing, n_top_features),
            "phishing_lgbm": self.clf_phishing_lgbm.debug_domain(
                domain_name, df, n_top_features
            )
            # TODO: Add explanations for other classifiers
        }
    

    def run_classifiers(self, df: pd.DataFrame, stats: pd.DataFrame):
        """
        Runs all classifiers on the input data (df) and stores the results.

            Args:
                df (pd.DataFrame): Input data containing a feature vector for each domain
                stats (pd.DataFrame): Statistics DataFrame to store classifier results

            Returns:
                Updated DataFrame with results
        """

        # Get individual classifiers' results
        # Phishing
        #stats["phishing_cnn_result"] = self.clf_phishing_cnn.classify(df)
        stats["phishing_lgbm_result"] = self.clf_phishing_lgbm.classify(df)
        stats["phishing_xgboost_result"] = self.clf_phishing_xgboost.classify(df)
        #stats["phishing_deepnn_result"] = self.clf_phishing_deepnn.classify(df)
        stats["phishing_dns_nn_result"] = self.clf_phishing_dns_nn.classify(df)
        stats["phishing_rdap_nn_result"] = self.clf_phishing_rdap_nn.classify(df)
        #stats["phishing_ip_nn_result"] = self.clf_phishing_ip_nn.classify(df)
        stats["phishing_html_lgbm_result"] = self.clf_phishing_html_lgbm.classify(df)

        # Malware
        stats["malware_lgbm_result"] = self.clf_malware_lgbm.classify(df)
        #stats["malware_xgboost_result"] = self.clf_malware_xgboost.classify(df)
        #stats["malware_deepnn_result"] = self.clf_malware_deepnn.classify(df)
        stats["malware_html_lgbm_result"] = self.clf_malware_html_lgbm.classify(df)

        # DGA
        stats["dga_binary_deepnn_result"] = self.clf_dga_binary_nn.classify(df)
        stats["dga_binary_lgbm_result"] = self.clf_dga_binary_lgbm.classify(df)


        return stats
    

    def compute_category_derived_stats(self, keys, prefix, stats):
        """
        Computes derived statistics (_sum, _avg, _prod) for a given category.
        If the classifier result is -1, the value is  ignored.

        Note: as a last-resort solution for an edge-case where no classifiers were usable for a category,
              the default value is set to 0.5.

        Args:
            keys (list): List of keys corresponding to classifier results in stats.
            prefix (str): The prefix for the category (e.g., "phishing", "malware").
            stats (pd.DataFrame): DataFrame containing the classifier results and derived statistics.

        Returns:
            Updated dataframe with the derived statistics.
        """
        # Mask valid values (exclude -1)
        valid_mask = stats[keys] != -1

        # Sum across valid values only
        stats[f"{prefix}_sum"] = stats[keys].where(valid_mask, 0).sum(axis=1)

        # Count valid values for averaging
        valid_counts = valid_mask.sum(axis=1)

        # Calculate average: sum / count, default to 0.5 if no valid values
        stats[f"{prefix}_avg"] = stats[f"{prefix}_sum"] / valid_counts
        stats[f"{prefix}_avg"].where(valid_counts > 0, 0.5, inplace=True)

        # Calculate product of valid values, replace -1 with 1 for ignored entries
        stats[f"{prefix}_prod"] = stats[keys].where(valid_mask, 1).prod(axis=1)
        stats[f"{prefix}_prod"].where(valid_counts > 0, 0.5 ** len(keys), inplace=True)

        return stats


    def compute_all_derived_stats(self, stats: pd.DataFrame) -> pd.DataFrame:
        """
        Computes derived statistics (_sum, _avg, _prod) for:
        * all categories (phishing_, malware_, dga_binary_)
        * all classifiers (total_ stats)
        Those derived statistics serve as additional inputs for the decision-making model.

        If the classifier result is -1, the value is ignored.
        
        Note: In an edge case that some category fails to produce any results, it is
        handled as if all the classifiers returned 0.5.

        Args:
            stats (pd.DataFrame): DataFrame containing the classifier results.

        Returns:
            Updated dataframe with the derived statistics.
        """
        
        phishing_keys = [key for key in stats.keys() if key.startswith("phishing_")]
        malware_keys = [key for key in stats.keys() if key.startswith("malware_")]
        dga_binary_keys = [key for key in stats.keys() if key.startswith("dga_binary_")]

        # Calculate derived statistics (sums, averages, products) for each category
        stats = self.compute_category_derived_stats(phishing_keys, "phishing", stats)
        stats = self.compute_category_derived_stats(malware_keys, "malware", stats)
        stats = self.compute_category_derived_stats(dga_binary_keys, "dga_binary", stats)

        # Calculate total derived statistics
        stats["total_sum"] = (
            stats["phishing_sum"] + stats["malware_sum"] + stats["dga_binary_sum"]
        )

        # Calculate row-wise valid classifier counts
        all_keys = phishing_keys + malware_keys + dga_binary_keys
        total_valid_mask = stats[all_keys] != -1
        stats["total_valid_classifiers"] = total_valid_mask.sum(axis=1)

        # Compute total_avg safely
        stats["total_avg"] = stats["total_sum"] / stats["total_valid_classifiers"]
        stats["total_avg"].where(stats["total_valid_classifiers"] > 0, 0.5, inplace=True)

        # Compute total_prod safely
        stats["total_prod"] = (
            stats["phishing_prod"] * stats["malware_prod"] * stats["dga_binary_prod"]
        )

        # For rows where no valid classifiers were available, set default product
        default_prod = 0.5 ** len(all_keys)
        stats.loc[stats["total_valid_classifiers"] == 0, "total_prod"] = default_prod

        # Clean up intermediate helper column
        stats.drop(columns=["total_valid_classifiers"], inplace=True)

        return stats

        # Note: DGA Multiclass is run seperately as it not used for the decision-making model


    def classify_domains(self, df: pd.DataFrame) -> list[dict]:
        """
        Classifies the domains from a pandas df and returns list the results.
        Each row of the input DF is a single domain, represented by a column  domain_name
        and
        """

        # Rearrange the feature vector to the order in which it was used in training
        df = df.reindex(columns=features_in_expected_order, copy=False)

        # Calculate the feature statistics
        stats = self.feature_statistics(df)

        # Perform classifications
        stats = self.run_classifiers(df, stats)

        # Calculte derived staistics (sums, averages, products)
        stats = self.compute_all_derived_stats(stats)

        # Calculate the overall badness probability
        stats["badness_probability"] = stats.apply(
            self.calculate_badness_probability, axis=1
        )

        # Estimate the most probable DGA Families
        stats["dga_families"] = self.clf_dga_multiclass_lgbm.classify(df)

        # Create an array of results
        results = stats.apply(
            lambda domain_stats: self.generate_result(domain_stats), axis=1
        ).tolist()

        return results
