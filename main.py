import torch
import pandas as pd
import numpy as np
import joblib
from typing import List, Dict
import warnings

warnings.filterwarnings('ignore')


class PredictionPipeline:
    def __init__(self, model_path: str = "action_model.pth"):
        """Инициализация пайплайна прогнозирования"""
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.load_model_and_artifacts(model_path)

    def load_model_and_artifacts(self, model_path: str):
        """Загрузка модели и артефактов"""
        try:
            # Загрузка артефактов
            self.le = joblib.load("label_encoder.pkl")
            self.scaler = joblib.load("scaler.pkl")

            # Загрузка модели
            checkpoint = torch.load(model_path, map_location=self.device)
            self.config = checkpoint['config']
            self.feature_columns = checkpoint['feature_columns']
            self.input_size = checkpoint['input_size']

            class ImprovedLSTMModel(torch.nn.Module):
                def __init__(self, input_size, hidden_size=64, num_layers=2):
                    super().__init__()
                    self.lstm = torch.nn.LSTM(
                        input_size=input_size,
                        hidden_size=hidden_size,
                        num_layers=num_layers,
                        batch_first=True
                    )
                    self.batch_norm = torch.nn.BatchNorm1d(hidden_size)
                    self.dropout = torch.nn.Dropout(0.2)
                    self.fc = torch.nn.Sequential(
                        torch.nn.Linear(hidden_size, hidden_size // 2),
                        torch.nn.ReLU(),
                        torch.nn.Dropout(0.2),
                        torch.nn.Linear(hidden_size // 2, 1)
                    )

                def forward(self, x):
                    lstm_out, _ = self.lstm(x)
                    last_out = lstm_out[:, -1, :]
                    mean_out = lstm_out.mean(dim=1)
                    combined = last_out + mean_out
                    combined = self.batch_norm(combined)
                    combined = self.dropout(combined)
                    output = self.fc(combined)
                    return output.squeeze()

            self.model = ImprovedLSTMModel(
                input_size=self.input_size,
                hidden_size=self.config['hidden_size'],
                num_layers=self.config['num_layers']
            )
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.model.to(self.device)
            self.model.eval()

            print(f"✅ Модель загружена успешно")
            print(f"   Устройство: {self.device}")
            print(f"   Входных признаков: {self.input_size}")
            print(f"   Длина последовательности: {self.config['sequence_length']}")

        except Exception as e:
            print(f"❌ Ошибка загрузки модели: {str(e)}")
            raise

    def create_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Создание временных признаков для новых данных"""
        df = df.copy()

        # Базовые признаки времени
        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['day_of_month'] = df['timestamp'].dt.day
        df['month'] = df['timestamp'].dt.month
        df['year'] = df['timestamp'].dt.year
        df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)

        # Циклические признаки
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
        df['day_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['day_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

        return df

    def prepare_features_for_prediction(self, df: pd.DataFrame, action: str) -> pd.DataFrame:
        """Подготовка признаков для конкретного действия"""
        df = df.copy()

        # Кодирование действия
        df['action_id'] = self.le.transform([action])[0]

        # Добавляем лаговые признаки для этого действия
        temp_counts = df['count'].copy()
        df['count_lag1'] = temp_counts.shift(1)
        df['count_rolling_mean_3'] = temp_counts.rolling(3, min_periods=1).mean()
        df['count_rolling_std_3'] = temp_counts.rolling(3, min_periods=1).std()

        # Заполняем пропуски
        df = df.fillna(method='bfill').fillna(method='ffill')

        # Нормализация count
        df['count_scaled'] = self.scaler.transform(df[['count']])

        # Создаем DataFrame со всеми нужными признаками
        features_df = pd.DataFrame()

        # Добавляем все необходимые признаки
        for col in self.feature_columns:
            if col in df.columns:
                features_df[col] = df[col]
            else:
                # Если признак отсутствует, заполняем нулями
                features_df[col] = 0
                print(f"⚠️  Признак {col} отсутствует, заполнен нулями")

        return features_df

    def predict_for_action(self, action_data: pd.DataFrame, action: str) -> Dict:
        """Прогнозирование для одного действия"""
        if len(action_data) < self.config['sequence_length']:
            return None

        # Подготовка признаков
        features_df = self.prepare_features_for_prediction(action_data, action)
        features_array = features_df.values

        # Берем последнюю последовательность
        X_seq = features_array[-self.config['sequence_length']:]
        X_tensor = torch.tensor(X_seq, dtype=torch.float32).unsqueeze(0).to(self.device)

        # Прогнозирование
        with torch.no_grad():
            pred_scaled = self.model(X_tensor).item()

        # Обратное преобразование масштаба
        # Создаем фиктивный массив для обратного преобразования
        dummy_array = np.zeros((1, len(self.feature_columns)))
        # Находим индекс count_scaled в feature_columns
        if 'count_scaled' in self.feature_columns:
            count_scaled_idx = self.feature_columns.index('count_scaled')
            dummy_array[0, count_scaled_idx] = pred_scaled

        # Получаем все обратно преобразованные значения
        try:
            pred_all = self.scaler.inverse_transform(dummy_array)
            pred_count = pred_all[0, count_scaled_idx]
        except:
            # Упрощенный подход если не работает inverse_transform
            pred_count = pred_scaled * self.scaler.scale_[0] + self.scaler.mean_[0]

        # Получаем фактические данные
        last_count = action_data['count'].iloc[-1]

        # Анализ отклонения
        deviation = last_count - pred_count
        deviation_percent = (deviation / pred_count * 100) if pred_count != 0 else 0

        # Определяем статус
        if abs(deviation_percent) > 50:
            status = "КРИТИЧЕСКОЕ ОТКЛОНЕНИЕ"
            alert = "🚨"
        elif deviation > 5:
            status = "Выше прогноза"
            alert = "▲"
        elif deviation < -5:
            status = "Ниже прогноза"
            alert = "▼"
        else:
            status = "В норме"
            alert = "✓"

        return {
            'action': action,
            'predicted_count': round(pred_count, 2),
            'actual_count': round(last_count, 2),
            'deviation': round(deviation, 2),
            'deviation_percent': round(deviation_percent, 1),
            'status': status,
            'alert': alert,
            'last_timestamp': action_data['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M'),
            'data_points': len(action_data),
            'has_enough_data': len(action_data) >= self.config['sequence_length']
        }

    def predict(self, new_data_path: str) -> List[Dict]:
        """Прогнозирование на новых данных"""
        print(f"\n📊 Загрузка данных для прогнозирования...")
        new_data = pd.read_csv(new_data_path, sep=';')
        new_data['timestamp'] = pd.to_datetime(new_data['timestamp'], format="%Y-%m-%d %H:%M")
        new_data = new_data.sort_values('timestamp')

        # Создаем временные признаки
        new_data = self.create_time_features(new_data)

        print(f"   Загружено {len(new_data)} строк")
        print(f"   Уникальных действий: {new_data['action'].nunique()}")

        results = []

        # Прогнозирование для каждого действия
        actions = new_data['action'].unique()
        print(f"\n🔍 Прогнозирование для {len(actions)} действий...")

        for i, action in enumerate(actions, 1):
            action_data = new_data[new_data['action'] == action].copy()
            action_data = action_data.sort_values('timestamp')

            print(f"   {i}. {action}: {len(action_data)} точек данных", end="")

            if len(action_data) < self.config['sequence_length']:
                print(f" - ❌ недостаточно данных")
                results.append({
                    'action': action,
                    'predicted_count': None,
                    'actual_count': action_data['count'].iloc[-1] if len(action_data) > 0 else None,
                    'deviation': None,
                    'deviation_percent': None,
                    'status': "Недостаточно данных",
                    'alert': "⚠️",
                    'last_timestamp': action_data['timestamp'].iloc[-1].strftime('%Y-%m-%d %H:%M') if len(
                        action_data) > 0 else None,
                    'data_points': len(action_data),
                    'has_enough_data': False
                })
                continue

            result = self.predict_for_action(action_data, action)
            if result:
                results.append(result)
                deviation_str = f"{result['deviation']:+.1f}"
                print(f" - прогноз: {result['predicted_count']:.1f}, отклонение: {deviation_str}")
            else:
                print(f" - ошибка прогнозирования")

        return results

    def print_report(self, results: List[Dict]):
        """Вывод аналитического отчета"""
        # Фильтруем только валидные результаты
        valid_results = [r for r in results if r['has_enough_data'] and r['predicted_count'] is not None]

        if not valid_results:
            print("\n❌ Нет данных для анализа")
            return

        print("\n" + "=" * 80)
        print("АНАЛИТИЧЕСКИЙ ОТЧЕТ ПО ПРОГНОЗИРОВАНИЮ")
        print("=" * 80)

        total_actions = len(valid_results)
        normal_count = sum(1 for r in valid_results if r['status'] == "В норме")
        warning_count = sum(1 for r in valid_results if "прогноза" in r['status'])
        critical_count = sum(1 for r in valid_results if "КРИТИЧЕСКОЕ" in r['status'])

        print(f"\n📈 ОБЩАЯ СТАТИСТИКА:")
        print(f"  Всего действий с прогнозами: {total_actions}")
        print(f"  • В норме: {normal_count} ({normal_count / total_actions * 100:.1f}%)")
        print(f"  • Отклонения: {warning_count} ({warning_count / total_actions * 100:.1f}%)")
        print(f"  • Критические: {critical_count} ({critical_count / total_actions * 100:.1f}%)")

        print(f"\n🔍 ДЕТАЛЬНЫЕ РЕЗУЛЬТАТЫ:")
        print("-" * 80)
        print(f"{'Действие':<25} {'Прогноз':<10} {'Факт':<10} {'Отклонение':<15} {'Статус':<20}")
        print("-" * 80)

        # Сортируем по абсолютному отклонению
        for result in sorted(valid_results,
                             key=lambda x: abs(x['deviation_percent']) if x['deviation_percent'] is not None else 0,
                             reverse=True):
            print(f"{result['action'][:23]:<25} "
                  f"{result['predicted_count']:<10.1f} "
                  f"{result['actual_count']:<10.1f} "
                  f"{result['deviation']:>+7.1f} ({result['deviation_percent']:>+6.1f}%) "
                  f"{result['alert']} {result['status']:<20}")

        # Рекомендации
        print(f"\n🚨 РЕКОМЕНДАЦИИ:")

        # Критические отклонения
        critical_actions = [r for r in valid_results if "КРИТИЧЕСКОЕ" in r['status']]
        if critical_actions:
            print("  Требуют немедленного внимания:")
            for action in critical_actions:
                print(f"    • {action['action']}: отклонение {action['deviation_percent']:+.1f}%")

        # Наибольшие отклонения
        top_deviations = sorted(valid_results,
                                key=lambda x: abs(x['deviation_percent']) if x['deviation_percent'] is not None else 0,
                                reverse=True)[:5]
        if top_deviations:
            print(f"\n  Наибольшие отклонения:")
            for i, action in enumerate(top_deviations, 1):
                if action['deviation_percent'] is not None:
                    print(f"    {i}. {action['action']}: {action['deviation_percent']:+.1f}%")

        # Статистика по времени
        print(f"\n📅 ПОСЛЕДНИЕ ДАННЫЕ:")
        latest_timestamp = max(r['last_timestamp'] for r in valid_results if r['last_timestamp'])
        print(f"  Последние данные на: {latest_timestamp}")


# -----------------------------
# Основной скрипт
# -----------------------------
def main():
    print("=" * 60)
    print("ПРОГНОЗИРОВАНИЕ НА ОСНОВЕ ОБУЧЕННОЙ МОДЕЛИ")
    print("=" * 60)

    try:
        # Инициализация пайплайна
        pipeline = PredictionPipeline("action_model.pth")

        # Прогнозирование
        results = pipeline.predict("2.csv")

        # Вывод отчета
        pipeline.print_report(results)

        # Сохранение результатов в CSV
        results_df = pd.DataFrame(results)
        results_df.to_csv("prediction_results.csv", index=False, encoding='utf-8-sig')
        print(f"\n💾 Результаты сохранены в 'prediction_results.csv'")

        # Создание краткого отчета
        summary = {
            'total_actions': len(results),
            'valid_predictions': len([r for r in results if r['has_enough_data']]),
            'normal': len([r for r in results if r.get('status') == 'В норме']),
            'warnings': len([r for r in results if r.get('status') in ['Выше прогноза', 'Ниже прогноза']]),
            'critical': len([r for r in results if 'КРИТИЧЕСКОЕ' in str(r.get('status'))])
        }

        print(f"\n✅ Прогнозирование завершено успешно!")
        print(f"   Всего обработано действий: {summary['total_actions']}")
        print(f"   Успешных прогнозов: {summary['valid_predictions']}")

    except FileNotFoundError as e:
        print(f"\n❌ Файл не найден: {e}")
        print("   Убедитесь, что файлы 'action_model.pth', 'label_encoder.pkl', 'scaler.pkl' существуют")
    except Exception as e:
        print(f"\n❌ Ошибка: {str(e)}")


if __name__ == "__main__":
    main()

# import pandas as pd
# import numpy as np
# import torch
# import torch.nn as nn
# from torch.utils.data import Dataset, DataLoader, random_split
# from sklearn.preprocessing import LabelEncoder, StandardScaler
# import joblib
# from typing import Dict, Tuple, Optional
# import warnings
# import traceback
#
# warnings.filterwarnings('ignore')
#
# # Конфигурация
# CONFIG = {
#     'sequence_length': 24,
#     'batch_size': 32,
#     'hidden_size': 64,
#     'num_layers': 2,
#     'learning_rate': 0.001,
#     'epochs': 30,
#     'validation_split': 0.2,
#     'random_seed': 42
# }
#
#
# # Устанавливаем seed для воспроизводимости
# def set_seed(seed=42):
#     torch.manual_seed(seed)
#     np.random.seed(seed)
#     if torch.cuda.is_available():
#         torch.cuda.manual_seed_all(seed)
#
#
# set_seed(CONFIG['random_seed'])
#
# # Глобальная переменная для feature_columns
# feature_columns = []
#
#
# # -----------------------------
# # 1. Загрузка и подготовка данных
# # -----------------------------
# def load_and_prepare_data(filepath: str) -> pd.DataFrame:
#     """Загрузка и предобработка данных"""
#     df = pd.read_csv(filepath, sep=';')
#     df['timestamp'] = pd.to_datetime(df['timestamp'], format="%Y-%m-%d %H:%M")
#     return df.sort_values('timestamp')
#
#
# # -----------------------------
# # 2. Создание временных признаков
# # -----------------------------
# def create_time_features(df: pd.DataFrame) -> pd.DataFrame:
#     """Создание временных и циклических признаков"""
#     df = df.copy()
#
#     # Базовые признаки времени
#     df['hour'] = df['timestamp'].dt.hour
#     df['day_of_week'] = df['timestamp'].dt.dayofweek
#     df['day_of_month'] = df['timestamp'].dt.day
#     df['month'] = df['timestamp'].dt.month
#     df['year'] = df['timestamp'].dt.year
#     df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
#
#     # Циклические признаки (лучший подход)
#     df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
#     df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
#     df['day_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
#     df['day_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
#     df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
#     df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
#
#     # Сначала создаем все новые колонки
#     for col in ['count_lag1', 'count_rolling_mean_3', 'count_rolling_std_3']:
#         if col not in df.columns:
#             df[col] = np.nan
#
#     return df
#
#
# # -----------------------------
# # 3. Подготовка признаков
# # -----------------------------
# def prepare_features(df: pd.DataFrame,
#                      le: Optional[LabelEncoder] = None,
#                      scaler: Optional[StandardScaler] = None,
#                      fit: bool = True) -> Tuple[pd.DataFrame, LabelEncoder, StandardScaler]:
#     """Подготовка и нормализация признаков"""
#     df = df.copy()
#
#     # Кодирование действий
#     if le is None:
#         le = LabelEncoder()
#     if fit:
#         df['action_id'] = le.fit_transform(df['action'])
#     else:
#         df['action_id'] = le.transform(df['action'])
#
#     # Добавляем лаговые признаки для каждого действия
#     actions = df['action'].unique()
#     for action in actions:
#         action_mask = df['action'] == action
#
#         # Создаем временный DataFrame для этого действия
#         temp_df = df.loc[action_mask, 'count'].copy()
#
#         # Лаговые признаки
#         df.loc[action_mask, 'count_lag1'] = temp_df.shift(1)
#         df.loc[action_mask, 'count_rolling_mean_3'] = temp_df.rolling(3, min_periods=1).mean()
#         df.loc[action_mask, 'count_rolling_std_3'] = temp_df.rolling(3, min_periods=1).std()
#
#     # Заполняем пропуски
#     for col in ['count_lag1', 'count_rolling_mean_3', 'count_rolling_std_3']:
#         if col in df.columns:
#             df[col] = df[col].fillna(method='bfill').fillna(method='ffill')
#
#     # Создаем признак count_scaled
#     if scaler is None:
#         scaler = StandardScaler()
#
#     if fit:
#         df['count_scaled'] = scaler.fit_transform(df[['count']])
#     else:
#         df['count_scaled'] = scaler.transform(df[['count']])
#
#     return df, le, scaler
#
#
# # -----------------------------
# # 4. Улучшенный Dataset
# # -----------------------------
# class TimeSeriesDataset(Dataset):
#     def __init__(self, df: pd.DataFrame, sequence_length: int = 24):
#         self.sequence_length = sequence_length
#         self.data = []
#
#         # Глобальные feature_columns
#         global feature_columns
#
#         print(f"Создание датасета...")
#         print(f"Колонки в df: {df.columns.tolist()}")
#
#         # Определяем feature_columns если они еще не определены
#         if not feature_columns:
#             feature_columns = [
#                 'count_scaled', 'action_id', 'hour_sin', 'hour_cos',
#                 'day_sin', 'day_cos', 'month_sin', 'month_cos',
#                 'is_weekend', 'count_lag1', 'count_rolling_mean_3', 'count_rolling_std_3'
#             ]
#             # Оставляем только существующие колонки
#             feature_columns = [col for col in feature_columns if col in df.columns]
#
#         print(f"Используемые признаки: {feature_columns}")
#
#         # Группируем по действиям
#         for action_id in df['action_id'].unique():
#             action_data = df[df['action_id'] == action_id].copy()
#             action_data = action_data.sort_values('timestamp')
#
#             # Проверяем наличие всех признаков
#             missing_cols = [col for col in feature_columns if col not in action_data.columns]
#             if missing_cols:
#                 print(f"Предупреждение: для action_id {action_id} отсутствуют колонки: {missing_cols}")
#                 continue
#
#             # Берем только нужные колонки
#             action_features = action_data[feature_columns].values
#
#             # Создаем последовательности
#             for i in range(len(action_features) - sequence_length):
#                 X = action_features[i:i + sequence_length]
#                 # y - следующий count (не scaled)
#                 y = action_data.iloc[i + sequence_length]['count']
#
#                 self.data.append((X, y))
#
#         print(f"Создано {len(self.data)} последовательностей")
#
#     def __len__(self):
#         return len(self.data)
#
#     def __getitem__(self, idx):
#         X, y = self.data[idx]
#         return torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)
#
#
# # -----------------------------
# # 5. Улучшенная LSTM модель
# # -----------------------------
# class ImprovedLSTMModel(nn.Module):
#     def __init__(self, input_size: int, hidden_size: int = 64,
#                  num_layers: int = 2, dropout: float = 0.2):
#         super().__init__()
#
#         self.lstm = nn.LSTM(
#             input_size=input_size,
#             hidden_size=hidden_size,
#             num_layers=num_layers,
#             batch_first=True,
#             dropout=dropout if num_layers > 1 else 0,
#             bidirectional=False
#         )
#
#         # Добавляем BatchNorm и Dropout
#         self.batch_norm = nn.BatchNorm1d(hidden_size)
#         self.dropout = nn.Dropout(dropout)
#
#         # Улучшенная полносвязная часть
#         self.fc = nn.Sequential(
#             nn.Linear(hidden_size, hidden_size // 2),
#             nn.ReLU(),
#             nn.Dropout(dropout),
#             nn.Linear(hidden_size // 2, 1)
#         )
#
#     def forward(self, x):
#         lstm_out, _ = self.lstm(x)
#
#         # Используем не только последний, но и усредненный выход
#         last_out = lstm_out[:, -1, :]  # Последний шаг
#         mean_out = lstm_out.mean(dim=1)  # Среднее по времени
#
#         # Объединяем признаки
#         combined = last_out + mean_out
#
#         # Применяем нормализацию и дропаут
#         combined = self.batch_norm(combined)
#         combined = self.dropout(combined)
#
#         # Прогноз
#         output = self.fc(combined)
#         return output.squeeze()
#
#
# # -----------------------------
# # 6. Обучение с валидацией
# # -----------------------------
# def train_model(model, train_loader, val_loader, epochs, device):
#     """Функция обучения с валидацией"""
#     optimizer = torch.optim.Adam(model.parameters(), lr=CONFIG['learning_rate'])
#
#     # Используем Huber loss для большей устойчивости
#     criterion = nn.HuberLoss()
#
#     # Планировщик скорости обучения (упрощенный для старых версий PyTorch)
#     try:
#         scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
#             optimizer, mode='min', factor=0.5, patience=3
#         )
#         use_scheduler = True
#     except:
#         print("Внимание: использование упрощенного планировщика LR")
#         scheduler = None
#         use_scheduler = False
#
#     train_losses = []
#     val_losses = []
#
#     for epoch in range(epochs):
#         # Обучение
#         model.train()
#         train_loss = 0
#         for batch_idx, (X_batch, y_batch) in enumerate(train_loader):
#             X_batch, y_batch = X_batch.to(device), y_batch.to(device)
#
#             # Проверка размеров
#             if X_batch.shape[0] == 0:
#                 continue
#
#             optimizer.zero_grad()
#             predictions = model(X_batch)
#
#             # Проверяем размеры предсказаний
#             if predictions.dim() == 0:
#                 predictions = predictions.unsqueeze(0)
#
#             loss = criterion(predictions, y_batch)
#             loss.backward()
#
#             # Gradient clipping для устойчивости
#             torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
#
#             optimizer.step()
#             train_loss += loss.item()
#
#         # Валидация
#         model.eval()
#         val_loss = 0
#         with torch.no_grad():
#             for X_batch, y_batch in val_loader:
#                 X_batch, y_batch = X_batch.to(device), y_batch.to(device)
#
#                 if X_batch.shape[0] == 0:
#                     continue
#
#                 predictions = model(X_batch)
#
#                 if predictions.dim() == 0:
#                     predictions = predictions.unsqueeze(0)
#
#                 loss = criterion(predictions, y_batch)
#                 val_loss += loss.item()
#
#         # Средние потери
#         avg_train_loss = train_loss / len(train_loader) if len(train_loader) > 0 else 0
#         avg_val_loss = val_loss / len(val_loader) if len(val_loader) > 0 else 0
#
#         train_losses.append(avg_train_loss)
#         val_losses.append(avg_val_loss)
#
#         # Обновление LR
#         if use_scheduler and scheduler is not None:
#             scheduler.step(avg_val_loss)
#
#         # Вывод прогресса
#         if (epoch + 1) % 5 == 0 or epoch == 0:
#             current_lr = optimizer.param_groups[0]['lr']
#             print(f"Epoch {epoch + 1}/{epochs}")
#             print(f"  Train Loss: {avg_train_loss:.4f}")
#             print(f"  Val Loss:   {avg_val_loss:.4f}")
#             print(f"  LR:         {current_lr:.6f}")
#
#     return train_losses, val_losses
#
#
# # -----------------------------
# # 7. Основной пайплайн
# # -----------------------------
# def main():
#     try:
#         print("=" * 60)
#         print("ОБУЧЕНИЕ МОДЕЛИ ПРОГНОЗИРОВАНИЯ")
#         print("=" * 60)
#
#         print("\n1. Загрузка данных...")
#         df = load_and_prepare_data("training_data.csv")
#         print(f"   Загружено {len(df)} строк")
#         print(f"   Уникальных действий: {df['action'].nunique()}")
#
#         print("\n2. Создание признаков...")
#         df = create_time_features(df)
#         print(f"   Создано {len(df.columns)} признаков")
#
#         print("\n3. Подготовка признаков...")
#         df, le, scaler = prepare_features(df, fit=True)
#         print(f"   Уникальных action_id: {df['action_id'].nunique()}")
#
#         # Сохраняем подготовленные данные
#         print("\n4. Сохранение артефактов...")
#         joblib.dump(le, "label_encoder.pkl")
#         joblib.dump(scaler, "scaler.pkl")
#         print("   Артефакты сохранены")
#
#         # Определяем feature_columns
#         global feature_columns
#         feature_columns = [
#             'count_scaled', 'action_id', 'hour_sin', 'hour_cos',
#             'day_sin', 'day_cos', 'month_sin', 'month_cos',
#             'is_weekend', 'count_lag1', 'count_rolling_mean_3', 'count_rolling_std_3'
#         ]
#         # Оставляем только существующие колонки
#         feature_columns = [col for col in feature_columns if col in df.columns]
#
#         print(f"\n5. Используемые признаки ({len(feature_columns)}):")
#         for i, col in enumerate(feature_columns, 1):
#             print(f"   {i:2d}. {col}")
#
#         print("\n6. Создание датасета...")
#         dataset = TimeSeriesDataset(df, sequence_length=CONFIG['sequence_length'])
#
#         # Разделение на train/val
#         val_size = int(CONFIG['validation_split'] * len(dataset))
#         train_size = len(dataset) - val_size
#         train_dataset, val_dataset = random_split(dataset, [train_size, val_size])
#
#         train_loader = DataLoader(train_dataset, batch_size=CONFIG['batch_size'],
#                                   shuffle=True, num_workers=0)  # 0 для избежания проблем
#         val_loader = DataLoader(val_dataset, batch_size=CONFIG['batch_size'],
#                                 shuffle=False, num_workers=0)
#
#         print(f"   Train samples: {len(train_dataset)}, Val samples: {len(val_dataset)}")
#         print(f"   Batch size: {CONFIG['batch_size']}")
#
#         # Создание модели
#         device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
#         print(f"\n7. Создание модели (устройство: {device})...")
#
#         input_size = len(feature_columns)
#         model = ImprovedLSTMModel(
#             input_size=input_size,
#             hidden_size=CONFIG['hidden_size'],
#             num_layers=CONFIG['num_layers']
#         ).to(device)
#
#         param_count = sum(p.numel() for p in model.parameters())
#         print(f"   Размер модели: {param_count:,} параметров")
#         print(f"   Входной размер: {input_size}")
#         print(f"   Скрытый размер: {CONFIG['hidden_size']}")
#         print(f"   Количество слоев LSTM: {CONFIG['num_layers']}")
#
#         # Обучение
#         print("\n" + "=" * 60)
#         print("НАЧАЛО ОБУЧЕНИЯ")
#         print("=" * 60)
#
#         train_losses, val_losses = train_model(
#             model, train_loader, val_loader,
#             CONFIG['epochs'], device
#         )
#
#         # Сохранение модели
#         print("\n8. Сохранение модели...")
#         torch.save({
#             'model_state_dict': model.state_dict(),
#             'config': CONFIG,
#             'feature_columns': feature_columns,
#             'input_size': input_size,
#             'train_losses': train_losses,
#             'val_losses': val_losses
#         }, "action_model.pth")
#
#         print("   Модель сохранена в 'action_model.pth'")
#
#         # Сохранение истории обучения
#         history_df = pd.DataFrame({
#             'epoch': range(1, len(train_losses) + 1),
#             'train_loss': train_losses,
#             'val_loss': val_losses
#         })
#         history_df.to_csv("training_history.csv", index=False)
#         print("   История обучения сохранена в 'training_history.csv'")
#
#         print("\n" + "=" * 60)
#         print("ОБУЧЕНИЕ ЗАВЕРШЕНО")
#         print("=" * 60)
#         print(f"\nСтатистика обучения:")
#         print(f"  Final Train Loss: {train_losses[-1]:.4f}")
#         print(f"  Final Val Loss:   {val_losses[-1]:.4f}")
#
#         if len(train_losses) > 1:
#             improvement = ((train_losses[0] - train_losses[-1]) / train_losses[0]) * 100
#             print(f"  Улучшение за обучение: {improvement:.1f}%")
#
#     except Exception as e:
#         print(f"\n❌ ОШИБКА: {str(e)}")
#         print("\nТрассировка ошибки:")
#         traceback.print_exc()
#         return
#
#
# if __name__ == "__main__":
#     main()
#
# # # predict_model.py
# # import torch
# # import pandas as pd
# # import numpy as np
# # import joblib
# #
# # # -----------------------------
# # # 1. Загружаем scaler и LabelEncoder
# # # -----------------------------
# # scaler = joblib.load("scaler.pkl")
# # le = joblib.load("label_encoder.pkl")
# #
# # # -----------------------------
# # # 2. Определяем LSTM модель
# # # -----------------------------
# # class LSTMModel(torch.nn.Module):
# #     def __init__(self, input_size=5, hidden_size=64, num_layers=2):
# #         super().__init__()
# #         self.lstm = torch.nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
# #         self.fc = torch.nn.Linear(hidden_size, 1)
# #
# #     def forward(self, x):
# #         out, _ = self.lstm(x)
# #         out = out[:, -1, :]
# #         out = self.fc(out)
# #         return out.squeeze()
# #
# # model = LSTMModel()
# # model.load_state_dict(torch.load("lstm_model_weights.pth", map_location="cpu"))
# # model.eval()
# #
# # # -----------------------------
# # # 3. Загружаем новые данные
# # # -----------------------------
# # new_data = pd.read_csv("3.csv", sep=';')
# # new_data['timestamp'] = pd.to_datetime(new_data['timestamp'], format="%Y-%m-%d %H:%M")
# #
# # # Признаки времени
# # new_data['hour'] = new_data['timestamp'].dt.hour
# # new_data['day_of_week'] = new_data['timestamp'].dt.dayofweek
# # new_data['month'] = new_data['timestamp'].dt.month
# # new_data['sin_hour'] = np.sin(2 * np.pi * new_data['hour']/24)
# # new_data['cos_hour'] = np.cos(2 * np.pi * new_data['hour']/24)
# #
# # # Кодируем действия
# # new_data['action_id'] = le.transform(new_data['action'])
# #
# # # Нормализуем количество
# # new_data['count_scaled'] = scaler.transform(new_data[['count']])
# #
# # sequence_length = 24
# #
# # # -----------------------------
# # # 4. Прогнозирование и аналитика
# # # -----------------------------
# # results = []
# #
# # for action_id in new_data['action_id'].unique():
# #     g = new_data[new_data['action_id']==action_id].sort_values('timestamp')
# #     values = g[['count_scaled', 'sin_hour', 'cos_hour', 'day_of_week', 'month']].values
# #     if len(values) < sequence_length:
# #         continue
# #     X_seq = torch.tensor(values[-sequence_length:], dtype=torch.float32).unsqueeze(0)
# #     pred_scaled = model(X_seq).item()
# #     pred_count = scaler.inverse_transform([[pred_scaled]])[0][0]
# #     results.append({
# #         'action': le.inverse_transform([action_id])[0],
# #         'predicted_count': pred_count,
# #         'last_count': g['count'].values[-1]
# #     })
# #
# # # -----------------------------
# # # 5. Вывод аналитической справки
# # # -----------------------------
# # print("=== Аналитическая справка ===")
# # for r in results:
# #     diff = r['last_count'] - r['predicted_count']
# #     status = "норма"
# #     if diff > 5:
# #         status = "выше нормы"
# #     elif diff < -5:
# #         status = "ниже нормы"
# #     print(f"{r['action']}: текущее {r['last_count']:.1f}, прогноз {r['predicted_count']:.1f} → {status}")