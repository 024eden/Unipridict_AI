"""
UniPredict AI - Advanced Student Performance Prediction System
A comprehensive ML-based system for academic outcome prediction
"""

import os

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, roc_auc_score, roc_curve
from sklearn.feature_selection import SelectKBest, f_classif
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

class UniPredictAI:
    """Advanced Student Performance Prediction System"""
    
    def __init__(self):
        self.models = {}
        self.best_model = None
        self.scaler = StandardScaler()
        self.label_encoders = {}
        self.feature_importance = None
        self.X_train = None
        self.X_test = None
        self.y_train = None
        self.y_test = None
        self.feature_names = None
        
    def generate_sample_dataset(self, n_samples=5000):
        """Generate realistic synthetic student dataset"""
        np.random.seed(42)
        
        # Student demographics
        gender = np.random.choice(['Male', 'Female'], n_samples)
        age = np.random.randint(15, 25, n_samples)
        
        # Academic features
        attendance_rate = np.random.uniform(40, 100, n_samples)
        study_hours_weekly = np.random.gamma(3, 2, n_samples).clip(0, 40)
        previous_grades = np.random.uniform(30, 100, n_samples)
        assignment_completion = np.random.uniform(30, 100, n_samples)
        
        # Behavioral features
        class_participation = np.random.uniform(1, 10, n_samples)
        extra_curricular = np.random.choice(['Yes', 'No'], n_samples, p=[0.6, 0.4])
        library_visits = np.random.poisson(3, n_samples)
        online_resource_usage = np.random.uniform(0, 20, n_samples)
        
        # Socioeconomic features
        parent_education = np.random.choice(['High School', 'Bachelor', 'Master', 'PhD'], n_samples, p=[0.3, 0.4, 0.2, 0.1])
        family_income = np.random.choice(['Low', 'Medium', 'High'], n_samples, p=[0.3, 0.5, 0.2])
        internet_access = np.random.choice(['Yes', 'No'], n_samples, p=[0.8, 0.2])
        
        # Academic support
        tutoring = np.random.choice(['Yes', 'No'], n_samples, p=[0.4, 0.6])
        mentor_support = np.random.choice(['Yes', 'No'], n_samples, p=[0.3, 0.7])
        
        # Psychological factors
        stress_level = np.random.uniform(1, 10, n_samples)
        motivation_score = np.random.uniform(1, 10, n_samples)
        
        # Calculate final performance (target variable)
        performance_score = (
            attendance_rate * 0.25 +
            study_hours_weekly * 1.5 +
            previous_grades * 0.3 +
            assignment_completion * 0.2 +
            class_participation * 2 +
            motivation_score * 3 +
            np.where(extra_curricular == 'Yes', 5, 0) +
            np.where(tutoring == 'Yes', 8, 0) +
            np.where(internet_access == 'Yes', 3, 0) -
            stress_level * 1.5 +
            np.random.normal(0, 10, n_samples)  # Add noise
        )
        
        # Create performance categories
        performance_category = pd.cut(performance_score, 
                                     bins=[-np.inf, 50, 70, 85, np.inf],
                                     labels=['At Risk', 'Below Average', 'Average', 'Excellent'])
        
        # Create binary pass/fail
        pass_fail = np.where(performance_score >= 60, 'Pass', 'Fail')
        
        # Create DataFrame
        df = pd.DataFrame({
            'student_id': range(1, n_samples + 1),
            'gender': gender,
            'age': age,
            'attendance_rate': attendance_rate.round(2),
            'study_hours_weekly': study_hours_weekly.round(1),
            'previous_grades': previous_grades.round(2),
            'assignment_completion': assignment_completion.round(2),
            'class_participation': class_participation.round(1),
            'extra_curricular': extra_curricular,
            'library_visits': library_visits,
            'online_resource_hours': online_resource_usage.round(1),
            'parent_education': parent_education,
            'family_income': family_income,
            'internet_access': internet_access,
            'tutoring': tutoring,
            'mentor_support': mentor_support,
            'stress_level': stress_level.round(1),
            'motivation_score': motivation_score.round(1),
            'final_grade': performance_score.round(2),
            'performance_category': performance_category,
            'pass_fail': pass_fail
        })
        
        return df
    
    def preprocess_data(self, df, target_column='pass_fail'):
        """Advanced data preprocessing with feature engineering"""
        print("=" * 60)
        print("DATA PREPROCESSING & FEATURE ENGINEERING")
        print("=" * 60)
        
        # Create a copy
        data = df.copy()
        
        # Feature Engineering
        print("\nCreating engineered features...")
        
        # Engagement score
        data['engagement_score'] = (
            data['attendance_rate'] * 0.4 +
            data['class_participation'] * 10 +
            data['assignment_completion'] * 0.5
        ) / 3
        
        # Study efficiency
        data['study_efficiency'] = data['previous_grades'] / (data['study_hours_weekly'] + 1)
        
        # Support index
        support_score = 0
        if 'tutoring' in data.columns:
            support_score += np.where(data['tutoring'] == 'Yes', 1, 0)
        if 'mentor_support' in data.columns:
            support_score += np.where(data['mentor_support'] == 'Yes', 1, 0)
        if 'internet_access' in data.columns:
            support_score += np.where(data['internet_access'] == 'Yes', 1, 0)
        data['support_index'] = support_score
        
        # Behavioral score
        data['behavioral_score'] = (
            data['class_participation'] * 0.4 +
            data['motivation_score'] * 0.4 -
            data['stress_level'] * 0.2
        )
        
        # Resource utilization
        data['resource_utilization'] = data['library_visits'] + data['online_resource_hours']
        
        # Age group categorization
        data['age_group'] = pd.cut(data['age'], bins=[0, 18, 21, 100], labels=['Teen', 'Young Adult', 'Adult'])
        
        print("Feature engineering completed")
        print(f"   Total features created: 6 new features")
        
        # Separate features and target
        # Drop non-predictive metadata columns and the target variable
        cols_to_drop = [
            'student_id', target_column, 'final_grade', 'performance_category',
            'student_name', 'parent_name', 'parent_email', 'address',
            'last_reported_at', 'reported_by', 'counselor_reported', 'added_by',
            'created_at', 'updated_at'
        ]
        X = data.drop(cols_to_drop, axis=1, errors='ignore')
        y = data[target_column]
        
        # Store feature names before encoding
        self.feature_names = X.columns.tolist()
        
        # Encode categorical variables
        print("\nEncoding categorical variables...")
        categorical_columns = X.select_dtypes(include=['object', 'category']).columns
        
        for col in categorical_columns:
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col].astype(str))
            self.label_encoders[col] = le
            print(f"   ✓ Encoded: {col}")
        
        # Handle missing values
        if X.isnull().sum().sum() > 0:
            print("\nHandling missing values...")
            X = X.fillna(X.mean())
        
        # Encode target variable
        if y.dtype == 'object':
            le_target = LabelEncoder()
            y = le_target.fit_transform(y)
            self.label_encoders['target'] = le_target
            print(f"\nTarget classes: {le_target.classes_}")
        
        print(f"\nDataset shape: {X.shape}")
        print(f"   Features: {X.shape[1]}")
        print(f"   Samples: {X.shape[0]}")
        
        return X, y
    
    def feature_selection(self, X, y, k=15):
        """Select top k features using statistical tests"""
        print("\n" + "=" * 60)
        print("FEATURE SELECTION")
        print("=" * 60)
        
        selector = SelectKBest(score_func=f_classif, k=min(k, X.shape[1]))
        X_selected = selector.fit_transform(X, y)
        
        # Get feature scores
        feature_scores = pd.DataFrame({
            'Feature': self.feature_names,
            'Score': selector.scores_
        }).sort_values('Score', ascending=False)
        
        print("\nTop Features by Importance:")
        print(feature_scores.head(10).to_string(index=False))
        
        selected_features = [self.feature_names[i] for i in selector.get_support(indices=True)]
        self.selected_features = selected_features  # Store for prediction
        
        return X_selected, selected_features
    
    def train_models(self, X, y, use_feature_selection=True):
        """Train multiple ML models with hyperparameter tuning"""
        print("\n" + "=" * 60)
        print("MODEL TRAINING")
        print("=" * 60)
        
        # Feature selection
        if use_feature_selection:
            X, selected_features = self.feature_selection(X, y)
            print(f"\nSelected {len(selected_features)} features")
        
        # Split data
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(
            X, y, test_size=0.5, random_state=42, stratify=y
        )
        
        # Scale features
        self.X_train = self.scaler.fit_transform(self.X_train)
        self.X_test = self.scaler.transform(self.X_test)
        
        print(f"\nTraining set: {self.X_train.shape[0]} samples")
        print(f"Testing set: {self.X_test.shape[0]} samples")
        
        # Define models
        models = {
            'Random Forest': RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1),
            'Gradient Boosting': GradientBoostingClassifier(n_estimators=100, random_state=42),
            'Logistic Regression': LogisticRegression(max_iter=1000, random_state=42),
            'SVM': SVC(probability=True, random_state=42)
        }
        
        print("\nTraining models...\n")
        results = []
        
        for name, model in models.items():
            print(f"Training {name}...", end=" ")
            
            # Train
            model.fit(self.X_train, self.y_train)
            
            # Predict
            y_pred = model.predict(self.X_test)
            
            # Evaluate
            accuracy = accuracy_score(self.y_test, y_pred)
            
            # Cross-validation
            cv_scores = cross_val_score(model, self.X_train, self.y_train, cv=5)
            cv_mean = cv_scores.mean()
            
            self.models[name] = model
            results.append({
                'Model': name,
                'Accuracy': accuracy,
                'CV Score': cv_mean,
                'CV Std': cv_scores.std()
            })
            
            print(f"Accuracy: {accuracy:.4f} | CV: {cv_mean:.4f}")
        
        # Results summary
        results_df = pd.DataFrame(results).sort_values('Accuracy', ascending=False)
        print("\n" + "=" * 60)
        print("MODEL PERFORMANCE SUMMARY")
        print("=" * 60)
        print(results_df.to_string(index=False))
        
        # Select best model
        best_model_name = results_df.iloc[0]['Model']
        self.best_model = self.models[best_model_name]
        
        print(f"\nBest Model: {best_model_name}")
        print(f"   Accuracy: {results_df.iloc[0]['Accuracy']:.4f}")
        
        # Create ensemble model
        print("\nCreating Ensemble Model...")
        ensemble = VotingClassifier(
            estimators=[(name, model) for name, model in self.models.items()],
            voting='soft'
        )
        ensemble.fit(self.X_train, self.y_train)
        ensemble_acc = accuracy_score(self.y_test, ensemble.predict(self.X_test))
        self.models['Ensemble'] = ensemble
        
        print(f"Ensemble Accuracy: {ensemble_acc:.4f}")
        
        if ensemble_acc > results_df.iloc[0]['Accuracy']:
            self.best_model = ensemble
            print("Ensemble is the best model!")
        
        return results_df
    
    def evaluate_model(self, model_name=None):
        """Detailed model evaluation"""
        if model_name is None:
            model = self.best_model
            model_name = "Best Model"
        else:
            model = self.models.get(model_name, self.best_model)
        
        print("\n" + "=" * 60)
        print(f"DETAILED EVALUATION: {model_name}")
        print("=" * 60)
        
        y_pred = model.predict(self.X_test)
        y_pred_proba = model.predict_proba(self.X_test)
        
        # Classification report
        print("\nClassification Report:")
        print(classification_report(self.y_test, y_pred))
        
        # Confusion Matrix
        cm = confusion_matrix(self.y_test, y_pred)
        print("\nConfusion Matrix:")
        print(cm)
        
        # ROC AUC Score
        try:
            roc_auc = roc_auc_score(self.y_test, y_pred_proba[:, 1], average='binary')
            print(f"\nROC AUC Score: {roc_auc:.4f}")
        except:
            print("\nROC AUC Score not available for multiclass")
        
        return y_pred, y_pred_proba
    
    def predict_new_student(self, student_data):
        """Predict performance for a new student"""
        # Create DataFrame
        df = pd.DataFrame([student_data])
        
        # Feature engineering (same as training)
        df['engagement_score'] = (
            df['attendance_rate'] * 0.4 +
            df['class_participation'] * 10 +
            df['assignment_completion'] * 0.5
        ) / 3
        
        df['study_efficiency'] = df['previous_grades'] / (df['study_hours_weekly'] + 1)
        
        support_score = 0
        if 'tutoring' in df.columns:
            support_score += np.where(df['tutoring'] == 'Yes', 1, 0)
        if 'mentor_support' in df.columns:
            support_score += np.where(df['mentor_support'] == 'Yes', 1, 0)
        if 'internet_access' in df.columns:
            support_score += np.where(df['internet_access'] == 'Yes', 1, 0)
        df['support_index'] = support_score
        
        df['behavioral_score'] = (
            df['class_participation'] * 0.4 +
            df['motivation_score'] * 0.4 -
            df['stress_level'] * 0.2
        )
        
        df['resource_utilization'] = df['library_visits'] + df['online_resource_hours']
        df['age_group'] = pd.cut(df['age'], bins=[0, 18, 21, 100], labels=['Teen', 'Young Adult', 'Adult'])
        
        # Encode categorical variables
        for col in df.select_dtypes(include=['object', 'category']).columns:
            if col in self.label_encoders:
                df[col] = self.label_encoders[col].transform(df[col].astype(str))
        
        # Select same features as training (only those that exist in df)
        available_features = [f for f in self.feature_names if f in df.columns]
        df = df[available_features]
        
        # Apply feature selection if used during training
        if hasattr(self, 'selected_features') and self.selected_features:
            available_selected = [f for f in self.selected_features if f in df.columns]
            df = df[available_selected]
        
        # Scale
        df_scaled = self.scaler.transform(df)
        
        # Predict
        prediction = self.best_model.predict(df_scaled)[0]
        probability = self.best_model.predict_proba(df_scaled)[0]
        
        # Decode prediction
        if 'target' in self.label_encoders:
            prediction = self.label_encoders['target'].inverse_transform([prediction])[0]
        
        return prediction, probability
    
    def visualize_results(self, save_path=None):
      if save_path is None:
        save_path = os.path.dirname(os.path.abspath(__file__)) + os.sep
        print(f"DEBUG save_path = {save_path}")  # ← add this temporarily
        """Create comprehensive visualizations"""
        print("\n" + "=" * 60)
        print("GENERATING VISUALIZATIONS")
        print("=" * 60)
        
        fig = plt.figure(figsize=(20, 12))
        
        # 1. Model Comparison
        ax1 = plt.subplot(2, 3, 1)
        model_names = list(self.models.keys())
        accuracies = [accuracy_score(self.y_test, model.predict(self.X_test)) 
                     for model in self.models.values()]
        
        colors = plt.cm.viridis(np.linspace(0, 1, len(model_names)))
        bars = ax1.barh(model_names, accuracies, color=colors)
        ax1.set_xlabel('Accuracy', fontsize=12, fontweight='bold')
        ax1.set_title('Model Performance Comparison', fontsize=14, fontweight='bold')
        ax1.set_xlim([0, 1])
        
        for i, bar in enumerate(bars):
            width = bar.get_width()
            ax1.text(width, bar.get_y() + bar.get_height()/2, 
                    f'{accuracies[i]:.3f}', 
                    ha='left', va='center', fontsize=10, fontweight='bold')
        
        # 2. Confusion Matrix
        ax2 = plt.subplot(2, 3, 2)
        cm = confusion_matrix(self.y_test, self.best_model.predict(self.X_test))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax2, cbar_kws={'label': 'Count'})
        ax2.set_title('Confusion Matrix - Best Model', fontsize=14, fontweight='bold')
        ax2.set_ylabel('True Label', fontsize=12)
        ax2.set_xlabel('Predicted Label', fontsize=12)
        
        # 3. ROC Curve
        ax3 = plt.subplot(2, 3, 3)
        try:
            y_pred_proba = self.best_model.predict_proba(self.X_test)[:, 1]
            fpr, tpr, _ = roc_curve(self.y_test, y_pred_proba)
            roc_auc = roc_auc_score(self.y_test, y_pred_proba[:, 1], average='binary')
            
            ax3.plot(fpr, tpr, color='darkorange', lw=2, 
                    label=f'ROC curve (AUC = {roc_auc:.3f})')
            ax3.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--', label='Random')
            ax3.set_xlim([0.0, 1.0])
            ax3.set_ylim([0.0, 1.05])
            ax3.set_xlabel('False Positive Rate', fontsize=12)
            ax3.set_ylabel('True Positive Rate', fontsize=12)
            ax3.set_title('ROC Curve', fontsize=14, fontweight='bold')
            ax3.legend(loc="lower right")
            ax3.grid(alpha=0.3)
        except:
            ax3.text(0.5, 0.5, 'ROC Curve\nNot Available\n(Multiclass)', 
                    ha='center', va='center', fontsize=12)
            ax3.set_title('ROC Curve', fontsize=14, fontweight='bold')
        
        # 4. Feature Importance (if Random Forest or Gradient Boosting)
        ax4 = plt.subplot(2, 3, 4)
        rf_model = self.models.get('Random Forest')
        if rf_model is not None and hasattr(rf_model, 'feature_importances_'):
            importances = rf_model.feature_importances_
            indices = np.argsort(importances)[-10:]

            if len(self.feature_names) == len(importances):
                features = [self.feature_names[i] for i in indices]
            else:
                features = [f'Feature {i}' for i in indices]

            ax4.barh(range(len(indices)), importances[indices], color='teal')
            ax4.set_yticks(range(len(indices)))
            ax4.set_yticklabels(features)
            ax4.set_xlabel('Importance', fontsize=12)
            ax4.set_title('Top 10 Feature Importances', fontsize=14, fontweight='bold')
        else:
            ax4.text(0.5, 0.5, 'Feature Importance\nNot Available', 
                     ha='center', va='center', fontsize=12)
            ax4.set_title('Feature Importance', fontsize=14, fontweight='bold')
        
        # 5. Class Distribution
        ax5 = plt.subplot(2, 3, 5)
        unique, counts = np.unique(self.y_test, return_counts=True)
        
        if 'target' in self.label_encoders:
            labels = self.label_encoders['target'].inverse_transform(unique)
        else:
            labels = unique
        
        colors_pie = plt.cm.Set3(range(len(unique)))
        wedges, texts, autotexts = ax5.pie(counts, labels=labels, autopct='%1.1f%%',
                                            colors=colors_pie, startangle=90)
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
        ax5.set_title('Test Set Class Distribution', fontsize=14, fontweight='bold')
        
        # 6. Prediction Confidence Distribution
        ax6 = plt.subplot(2, 3, 6)
        y_pred_proba = self.best_model.predict_proba(self.X_test)
        max_proba = np.max(y_pred_proba, axis=1)
        
        ax6.hist(max_proba, bins=20, color='mediumpurple', edgecolor='black', alpha=0.7)
        ax6.axvline(max_proba.mean(), color='red', linestyle='--', 
                   linewidth=2, label=f'Mean: {max_proba.mean():.3f}')
        ax6.set_xlabel('Prediction Confidence', fontsize=12)
        ax6.set_ylabel('Frequency', fontsize=12)
        ax6.set_title('Prediction Confidence Distribution', fontsize=14, fontweight='bold')
        ax6.legend()
        ax6.grid(alpha=0.3)
        
        plt.suptitle('UniPredict AI - Student Performance Analysis Dashboard', 
                    fontsize=18, fontweight='bold', y=0.98)
        plt.tight_layout(rect=[0, 0.03, 1, 0.96])
        
        # Save
        save_file = os.path.join(save_path, 'student_performance_analysis.png')
        plt.savefig(save_file, dpi=300, bbox_inches='tight')
        print(f"\nVisualizations saved: {save_file}")
        
        return save_file
    
    def identify_at_risk_students(self, df, threshold=0.6):
        """Identify students at risk of failing"""
        print("\n" + "=" * 60)
        print("AT-RISK STUDENT IDENTIFICATION")
        print("=" * 60)
        
        at_risk_students = []
        
        for idx, row in df.iterrows():
            student_data = row.to_dict()
            student_id = student_data.get('student_id', idx)
            
            # Remove target variables
            for col in ['pass_fail', 'final_grade', 'performance_category', 'student_id']:
                student_data.pop(col, None)
            
            try:
                prediction, probability = self.predict_new_student(student_data)
                
                # Check if at risk (high probability of failing)
                if 'target' in self.label_encoders:
                    fail_idx = list(self.label_encoders['target'].classes_).index('Fail')
                    fail_prob = probability[fail_idx]
                else:
                    fail_prob = 1 - probability[0]
                
                if fail_prob >= threshold:
                    at_risk_students.append({
                        'Student ID': student_id,
                        'Fail Probability': f"{fail_prob:.2%}",
                        'Attendance': f"{row['attendance_rate']:.1f}%",
                        'Study Hours': f"{row['study_hours_weekly']:.1f}",
                        'Previous Grade': f"{row['previous_grades']:.1f}",
                        'Recommendation': self._get_recommendation(row, fail_prob)
                    })
            except:
                continue
        
        if at_risk_students:
            risk_df = pd.DataFrame(at_risk_students)
            print(f"\nFound {len(at_risk_students)} at-risk students (threshold: {threshold:.0%})\n")
            print(risk_df.to_string(index=False))
            return risk_df
        else:
            print(f"\nNo at-risk students found (threshold: {threshold:.0%})")
            return None
    
    def _get_recommendation(self, student_row, fail_prob):
        """Generate personalized recommendations"""
        recommendations = []
        
        if student_row['attendance_rate'] < 75:
            recommendations.append("Improve attendance")
        if student_row['study_hours_weekly'] < 10:
            recommendations.append("Increase study time")
        if student_row['assignment_completion'] < 70:
            recommendations.append("Complete assignments")
        if student_row['stress_level'] > 7:
            recommendations.append("Stress management support")
        if student_row.get('tutoring', 'No') == 'No' and fail_prob > 0.7:
            recommendations.append("Enroll in tutoring")
        
        return '; '.join(recommendations) if recommendations else "Monitor progress"
    
    def generate_report(self, results_df, at_risk_df, save_path=None):
      if save_path is None:
        save_path = os.path.dirname(os.path.abspath(__file__)) + os.sep
        """Generate comprehensive PDF report"""
        report = []
        report.append("=" * 70)
        report.append("UNIPREDICT AI - STUDENT PERFORMANCE PREDICTION REPORT")
        report.append("=" * 70)
        report.append(f"\nGenerated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        report.append("\n" + "=" * 70)
        report.append("1. MODEL PERFORMANCE SUMMARY")
        report.append("=" * 70)
        report.append("\n" + results_df.to_string(index=False))
        
        report.append("\n\n" + "=" * 70)
        report.append("2. BEST MODEL DETAILS")
        report.append("=" * 70)
        
        y_pred = self.best_model.predict(self.X_test)
        report.append("\n" + classification_report(self.y_test, y_pred))
        
        if at_risk_df is not None:
            report.append("\n" + "=" * 70)
            report.append("3. AT-RISK STUDENTS")
            report.append("=" * 70)
            report.append("\n" + at_risk_df.to_string(index=False))
        
        report.append("\n\n" + "=" * 70)
        report.append("4. RECOMMENDATIONS")
        report.append("=" * 70)
        report.append("""
• Implement early intervention programs for at-risk students
• Provide additional tutoring and mentoring support
• Monitor attendance and engagement metrics closely
• Offer stress management and wellness programs
• Enhance parent-teacher communication
• Regular progress tracking and feedback sessions
        """)
        
        report.append("\n" + "=" * 70)
        report.append("END OF REPORT")
        report.append("=" * 70)
        
        report_text = '\n'.join(report)
        
        # Save report
        report_file = save_path + 'performance_report.txt'
        with open(report_file, 'w') as f:
            f.write(report_text)
        
        print(f"\n✅ Report saved: {report_file}")
        return report_file


def main():
    """Main execution function"""
    print("\n" + "=" * 70)
    print(" " * 15 + "🎓 UNIPREDICT AI 🎓")
    print(" " * 10 + "Student Performance Prediction System")
    print("=" * 70)
    
    # Initialize system
    predictor = UniPredictAI()
    
    # Generate dataset
    print("\nGenerating synthetic student dataset...")
    df = predictor.generate_sample_dataset(n_samples=5000)
    print(f"Generated {len(df)} student records")
    
    # Save dataset
    save_path = os.path.dirname(os.path.abspath(__file__)) + os.sep
    dataset_file = os.path.join(save_path, 'student_dataset.csv')

    df.to_csv(dataset_file, index=False)
    print(f"Dataset saved: {dataset_file}")
    
    # Preprocess
    X, y = predictor.preprocess_data(df, target_column='pass_fail')
    
    # Train models
    results_df = predictor.train_models(X, y, use_feature_selection=True)
    
    # Evaluate
    predictor.evaluate_model()
    
    # Visualize
    viz_file = predictor.visualize_results()
    
    # Identify at-risk students
    at_risk_df = predictor.identify_at_risk_students(df, threshold=0.6)
    
    # Generate report
    report_file = predictor.generate_report(results_df, at_risk_df)
    
    # Demo prediction
    print("\n" + "=" * 70)
    print("DEMO: PREDICTING NEW STUDENT PERFORMANCE")
    print("=" * 70)
    
    new_student = {
        'gender': 'Female',
        'age': 18,
        'attendance_rate': 65.0,
        'study_hours_weekly': 8.0,
        'previous_grades': 55.0,
        'assignment_completion': 60.0,
        'class_participation': 4.0,
        'extra_curricular': 'No',
        'library_visits': 2,
        'online_resource_hours': 5.0,
        'parent_education': 'High School',
        'family_income': 'Low',
        'internet_access': 'Yes',
        'tutoring': 'No',
        'mentor_support': 'No',
        'stress_level': 8.0,
        'motivation_score': 5.0
    }
    
    prediction, probability = predictor.predict_new_student(new_student)
    
    print("\nStudent Profile:")
    for key, value in new_student.items():
        print(f"   - {key}: {value}")
    
    print(f"\nPrediction: {prediction}")
    print(f"Confidence: {max(probability):.2%}")
    print(f"Probability Distribution: {probability}")
    
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE!")
    print("=" * 70)
    
    return predictor, df, viz_file, report_file, dataset_file


if __name__ == "__main__":
    predictor, df, viz_file, report_file, dataset_file = main()
