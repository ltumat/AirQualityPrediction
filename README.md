# AirQualityPrediction

Project corresponding to the course Scalable Machine Learning and Deep Learning (ID2223) at KTH. Team: LeScalable Frames (Jonas Lorenz and Álvaro Mazcuñán Herreros).

## Model training and deployment.

The notebooks for backfill, daily retrieval, training and prediction are in `backend/notebooks`. To run the code daily, we moved copies of the needed files to `backend/deployment`. There, you will find utilities, scripts to deploy on Modal and the notebooks that need to run daily.

The model was trained on data of 11 air quality sensors in Stockholm. The sensors are stored in a `.yml` file that can be found in backend/sensors. We tested different lag features, namely lags for 1, 2 and 3 days as well as lag averages for 2 and 3 days. The best performing model was the one using lag 1, so we used it for deployment. The feature was deemed most useful after averaging over models trained for each sensor by itself, scoring lowest on MSE and highest on R squared. The plots can be found in `backend/plots`.

## Public access

This project is currently deployed in the following URL: [https://lescalableframes.streamlit.app/](https://lescalableframes.streamlit.app/). As you can see in `app.py`, this is a basic Streamlit frontend that shows the map of the sensors with their current values for PM2.5 and its predictions for the next 6 days. You could also find an easter-egg in the frontend.
