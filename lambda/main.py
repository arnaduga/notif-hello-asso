import os
import sys
sys.path.insert(0, 'modules')
import boto3
import requests
import json
import logging
from datetime import datetime, timezone, timedelta
import csv
import io

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')
ssm_client = boto3.client('ssm')
sns_client = boto3.client('sns')

PAYMENT_STATE_TRANSLATIONS = {
    "Pending": "Paiement est planifiée à une date ultérieur, pas encore traité",
    "Authorized": "Paiement autorisé, validé et traité",
    "Refused": "Paiement refusé",
    "Registered": "Paiement fait hors ligne",
    "Refunded": "Paiement remboursé",
    "Refunding": "Paiement en cours de remboursement",
    "Contested": "Paiement contesté"
}

CASHOUT_STATE_TRANSLATIONS = {
    "CashedOut": "Versé sur le compte",
    "WaitingForCashOutConfirmation": "En attente de confirmation de versement",
    "Refunding" : "Paiement en cours de remboursement",
    "Refunded": "Paiement remboursé",
    "TransferInProgress": "Le paiement est en cours de transfert vers le compte",
    "Transfered": "Non versé"
}

def convert_json_to_csv(json_data_list):
    """
    Convertit une liste de dictionnaires JSON (données de paiement) en une chaîne CSV.

    Args:
        json_data_list (list): La liste des éléments JSON récupérés de l'API.

    Returns:
        str: Une chaîne contenant les données au format CSV, incluant l'en-tête.
             Retourne une chaîne vide avec seulement l'en-tête si json_data_list est vide.
    """
    if not json_data_list:
        logger.warning("La liste de données JSON à convertir en CSV est vide.")

    headers = [
        "Référence commande", "Référence du paiement", "Montant total", "Date du paiement",
        "Statut du paiement", "Versé", "Date du versement", "Nom payeur", "Prénom payeur",
        "Email payeur", "Date de naissance", "Raison sociale", "Adresse payeur",
        "Code postal payeur", "Ville payeur", "Montant du tarif", "Attestation",
        "Remboursement", "Status paiement (items)", "Description (items)"
    ]

    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)

    for payment in json_data_list:
        if not isinstance(payment, dict):
            logger.warning(f"Élément ignoré car ce n'est pas un dictionnaire : {payment}")
            continue

        order_info = payment.get('order', {}) or {} 
        payer_info = payment.get('payer', {}) or {} 
        items_list = payment.get('items', []) or [] 

        item_amounts = '/'.join([str(item.get('amount', 0) / 100) for item in items_list if isinstance(item, dict)])
        item_states = '/'.join([item.get('state', '') for item in items_list if isinstance(item, dict)])
        item_names = '/'.join([item.get('name', '') for item in items_list if isinstance(item, dict)])

        refund_ops = payment.get('refundOperations', [])
        formatted_refunds = []

        if isinstance(refund_ops, list):
            for refund in refund_ops:
                if isinstance(refund, dict):
                    try:
                        amount = refund.get('amount', 0) / 100
                        meta = refund.get('meta', {}) or {}
                        created_at_str = meta.get('createdAt')
                        if created_at_str:
                            created_at_dt = datetime.fromisoformat(created_at_str.replace('+02:00', '+0200'))
                            date_str = created_at_dt.strftime('%d/%m/%Y')
                            formatted_refunds.append(f"Remboursement de {amount:.2f} le {date_str}")
                        else:
                            formatted_refunds.append(f"Remboursement de {amount:.2f} (date inconnue)")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Erreur lors du formatage d'un remboursement pour paiement {payment.get('id', 'N/A')}: {e} - Données: {refund}")
                        formatted_refunds.append("Erreur formatage remboursement")
                else:
                     logger.warning(f"Élément de remboursement ignoré car ce n'est pas un dictionnaire : {refund}")
        else:
            logger.warning(f"Champ 'refundOperations' inattendu pour paiement {payment.get('id', 'N/A')}: {refund_ops}")

        refund_ops_str = "\n".join(formatted_refunds)

        # Look for translations into dictionnaries        
        original_payment_state = payment.get('state', '')
        translated_payment_state = PAYMENT_STATE_TRANSLATIONS.get(original_payment_state, original_payment_state)

        original_cashout_state = payment.get('cashOutState', '')
        translated_cashout_state = CASHOUT_STATE_TRANSLATIONS.get(original_cashout_state, original_cashout_state)


        row = [
            order_info.get('id', ''),
            payment.get('id', ''),
            payment.get('amount', 0) / 100,
            order_info.get('date', ''),
            translated_payment_state,
            translated_cashout_state,
            payment.get('cashOutDate', ''),
            payer_info.get('lastName', ''),
            payer_info.get('firstName', ''),
            payer_info.get('email', ''),
            payer_info.get('dateOfBirth', ''),
            payer_info.get('company', ''),
            payer_info.get('address', ''),
            payer_info.get('zipCode', ''),
            payer_info.get('city', ''),
            item_amounts,
            payment.get('paymentReceiptUrl', ''),
            refund_ops_str,
            item_states,
            item_names
        ]
        writer.writerow(row)

    csv_content = output.getvalue()
    output.close()
    logger.info(f"Conversion en CSV terminée. {len(json_data_list)} enregistrements traités.")
    return csv_content

def get_ssm_parameter(parameter_name, with_decryption=False):
    """Fetches a parameter from AWS Systems Manager Parameter Store."""
    try:
        response = ssm_client.get_parameter(
            Name=parameter_name,
            WithDecryption=with_decryption
        )
        return response['Parameter']['Value']
    except ssm_client.exceptions.ParameterNotFound:
        logger.error(f"SSM parameter not found: {parameter_name}")
        raise
    except Exception as e:
        logger.error(f"Error fetching SSM parameter {parameter_name}: {e}")
        raise

def get_api_token(token_url, client_id, client_secret):
    """Gets an OAuth token from the API."""
    try:
        payload = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        response = requests.post(token_url, data=payload, headers=headers, timeout=10)
        response.raise_for_status() 
        token_data = response.json()
        logger.info("Successfully obtained API token.")
        return token_data.get('access_token')
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting API token from {token_url}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during token retrieval: {e}")
        raise



def call_api(base_api_url, token, from_date_str=None, to_date_str=None):
    """
    Appelle l'API cible, gère la pagination via continuationToken et totalPages,
    et retourne une liste combinée des données.

    Hypothèses sur la structure de la réponse API :
    - Clé des données : 'data' (liste des éléments de la page)
    - Clé de pagination : 'pagination' (objet contenant les métadonnées)
    - Clés dans pagination : 'pageSize', 'totalCount', 'pageIndex', 'totalPages', 'continuationToken'

    Args:
        base_api_url (str): L'URL de base de l'API.
        token (str): Le jeton Bearer pour l'authentification.
        from_date_str (str, optional): Date de début (YYYY-MM-DD).
        to_date_str (str, optional): Date de fin (YYYY-MM-DD).

    Returns:
        list: Une liste contenant tous les éléments de données combinés de toutes les pages.
              Retourne une liste vide si l'appel initial échoue ou ne retourne aucune donnée.

    Raises:
        requests.exceptions.RequestException: Si une erreur réseau ou HTTP se produit.
        json.JSONDecodeError: Si une réponse de page n'est pas un JSON valide.
        KeyError: Si les clés attendues sont manquantes.
        Exception: Pour d'autres erreurs inattendues.
    """
    page_size = 100

    headers = {'Authorization': f'Bearer {token}'}
    params = {'pageSize': page_size}


    if from_date_str:
        params['from'] = from_date_str
    if to_date_str:
        params['to'] = to_date_str

    params['withCount'] = "true"

    logger.info(f"Appel de l'API (sans pagination) : {base_api_url}, Params: {params}")


    try:
        response = requests.get(base_api_url, headers=headers, params=params, timeout=30)
        response.raise_for_status() # Check for HTTP errors (4xx, 5xx)
        page_response = response.json()

        data_key = 'data'
        items = page_response.get(data_key)

        if items is not None and isinstance(items, list):
            logger.info(f"{len(items)} éléments récupérés depuis l'API.")
            return items
        else:
            logger.warning(f"Clé '{data_key}' non trouvée ou n'est pas une liste dans la réponse. Retour d'une liste vide.")
            return []

    except requests.exceptions.RequestException as e:
        if e.response is not None:
             logger.error(f"Erreur lors de l'appel API. Statut: {e.response.status_code}. Réponse: {e.response.text[:500]}")
        else:
             logger.error(f"Erreur lors de l'appel API: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Erreur de décodage JSON: {e}")
        try:
            logger.error(f"Texte de la réponse : {response.text[:500]}")
        except NameError:
            pass
        raise
    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'appel API: {e}", exc_info=True)
        raise

def save_to_s3_and_get_presigned_url(csv_content, bucket_name, environment, expiration_seconds):
    """
    Sauvegarde le contenu CSV sur S3 et génère une URL pré-signée pour les requêtes GET.

    Args:
        csv_content (str): Le contenu du fichier CSV sous forme de chaîne.
        bucket_name (str): Le nom du bucket S3.
        environment (str): L'environnement (ex: dev, prod) pour le préfixe S3.
        expiration_seconds (int): La durée de validité de l'URL pré-signée en secondes.

    Returns:
        tuple: Un tuple contenant (presigned_url, expiration_time)
               - presigned_url (str): L'URL pré-signée.
               - expiration_time (datetime): L'heure d'expiration de l'URL.
    """
    try:
        now_utc = datetime.now(timezone.utc)

        timestamp = now_utc.strftime("%Y-%m-%dT%H%M%SZ")
        folder = f"{now_utc.year}/{now_utc.month:02d}-{now_utc.day:02d}"
        s3_key = f"{environment}/{folder}/HelloAsso-Payemnets-Extract-{timestamp}.csv"
        logger.info(f"Uploading CSV data to s3://{bucket_name}/{s3_key}")

        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=csv_content.encode('utf-8'),
            ContentType='text/csv'
        )
        logger.info("Successfully uploaded CSV data to S3.")

        expiration_time = now_utc + timedelta(seconds=expiration_seconds)
        logger.info(f"Calculated expiration time: {expiration_time.isoformat()}")

        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': s3_key},
            ExpiresIn=expiration_seconds
        )
        logger.info(f"Generated presigned URL (expires in {expiration_seconds}s, {expiration_time.isoformat()}): {presigned_url}")

        return presigned_url, expiration_time

    except s3_client.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        logger.error(f"AWS S3 client error ({error_code}): {e}")
        raise
    except Exception as e:
        logger.error(f"Error saving CSV to S3 or generating presigned URL: {e}", exc_info=True) # Ajouter exc_info
        raise

def publish_sns_notification(topic_arn, subject, message):
    """Publishes a message to the specified SNS topic."""
    try:
        logger.info(f"Publishing notification to SNS topic: {topic_arn}")
        response = sns_client.publish(
            TopicArn=topic_arn,
            Message=message,
            Subject=subject
        )
        logger.info(f"Successfully published message to SNS (Message ID: {response.get('MessageId')})")
        return True
    except sns_client.exceptions.NotFoundException:
        logger.error(f"SNS topic not found: {topic_arn}")
        return False
    except sns_client.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        logger.error(f"AWS SNS client error ({error_code}) publishing to {topic_arn}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error publishing to SNS topic {topic_arn}: {e}", exc_info=True)
        return False

def lambda_handler(event, context):
    logger.info("Lambda execution started.")
    sns_topic_arn = None
    environment = os.environ.get('ENVIRONMENT', 'dev') 

    try:
        api_url_param = os.environ['API_URL_PARAM_NAME']
        token_url_param = os.environ['API_URL_TOKEN_PARAM_NAME']
        client_id_param = os.environ['API_CLIENT_ID_PARAM_NAME']
        client_secret_param = os.environ['API_CLIENT_SECRET_PARAM_NAME']
        s3_bucket_name = os.environ['S3_BUCKET_NAME']
        presigned_url_expiration_seconds = int(os.environ['PRESIGNED_URL_EXPIRATION'])
        sns_topic_arn = os.environ.get('SNS_TOPIC_ARN')


        # Récupérer les valeurs des paramètres depuis SSM
        logger.info("Fetching configuration from Parameter Store...")
        api_url = get_ssm_parameter(api_url_param)
        token_url = get_ssm_parameter(token_url_param)
        client_id = get_ssm_parameter(client_id_param, with_decryption=True)
        client_secret = get_ssm_parameter(client_secret_param, with_decryption=True)
        logger.info("Configuration fetched successfully.")

        # --- Calcul des dates (mois précédent complet) ---
        logger.info("Calculating 'from' and 'to' dates for the previous month...")
        today = datetime.now(timezone.utc).date()

        first_day_current_month = today.replace(day=1)
        to_date = first_day_current_month - timedelta(days=1)
        from_date = to_date.replace(day=1)
        from_date_str = from_date.strftime('%Y-%m-%d')
        to_date_str = to_date.strftime('%Y-%m-%d')
        logger.info(f"Calculated dates for previous month: from={from_date_str}, to={to_date_str}")

        # 1. Obtenir le token d'authentification
        logger.info("Getting API token...")
        api_token = get_api_token(token_url, client_id, client_secret)
        if not api_token:
            raise Exception("Failed to obtain API token.")

        # 2. Appeler l'API cible
        logger.info("Calling target API...")
        all_api_items = call_api(
            base_api_url=api_url,
            token=api_token,
            from_date_str=from_date_str,
            to_date_str=to_date_str
        )

        if all_api_items is None: 
             raise Exception("API call function returned None unexpectedly.")
        if not all_api_items:
            logger.warning("API call completed, but no items were retrieved after handling pagination.")

        # --- 3. Convertir les données JSON en CSV ---
        logger.info(f"Converting {len(all_api_items)} items to CSV format...")
        csv_data = convert_json_to_csv(all_api_items)



        # 4. Sauvegarder les résultats sur S3 et obtenir l'URL pré-signée
        logger.info("Saving CSV results to S3 and generating presigned URL...")
        result_url, expiration_datetime = save_to_s3_and_get_presigned_url(
            csv_content=csv_data, # Utiliser les données CSV
            bucket_name=s3_bucket_name,
            environment=environment,
            expiration_seconds=presigned_url_expiration_seconds
        )

        # 5. Publier l'URL pré-signée sur SNS (si l'ARN est configuré)
        if sns_topic_arn:
            logger.info("Preparing SNS notification...")

            expiration_str = expiration_datetime.strftime("%Y-%m-%d %H:%M:%S %Z")

            sns_subject = f"Extraction paiements HelloAsso : du {from_date_str} au {to_date_str}"

            warning_message = ""
            if len(all_api_items) == 100:
                warning_message = "ATTENTION : Le nombre d'enregistrements récupérés est exactement 100. Il est possible que toutes les données n'aient pas été extraites (limite de page atteinte sans pagination).\n\n"

            sns_message = (
                f"{warning_message}"
                f"Traitement HelloAsso terminé (pour l'environnement '{environment}').\n\n"
                f"Période couverte : du {from_date_str} au {to_date_str}\n"
                f"Nombre total d'enregistrements traités : {len(all_api_items)}\n\n" 
                f"Le fichier de résultats au format CSV est disponible via ce lien (valide jusqu'au {expiration_str}) :\n"
                f"{result_url}\n\n"
                f"(Bucket: {s3_bucket_name})"
            )

            publish_sns_notification(sns_topic_arn, sns_subject, sns_message)

        else:
            logger.warning("SNS_TOPIC_ARN environment variable not set. Skipping SNS notification.")

        logger.info("Lambda execution finished successfully.")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Processing complete for period {from_date_str} to {to_date_str}. Results saved as CSV to S3.', # Mentionner CSV
                'period_from': from_date_str,
                'period_to': to_date_str,
                'total_items_processed': len(all_api_items),
                'expires_at': expiration_datetime.isoformat(),
                'presigned_url': result_url
            })
        }



    except KeyError as e:
        logger.error(f"Missing environment variable: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'message': f'Configuration Error: Missing environment variable {e}'})
        }
    except Exception as e:
        logger.exception("Lambda execution failed!")
        if sns_topic_arn:
             from_date_val = locals().get('from_date_str', 'N/A')
             to_date_val = locals().get('to_date_str', 'N/A')
             page_val = locals().get('page_num', 'N/A')
             error_subject = f"ERREUR Traitement HelloAsso ({from_date_val} à {to_date_val}) - {environment}"
             error_message = (
                 f"L'exécution de la Lambda a échoué pour la période {from_date_val} à {to_date_val}.\n"
                 f"(Erreur potentiellement survenue lors du traitement de la page {page_val})\n"
                 f"Erreur: {str(e)}\nConsultez les logs CloudWatch pour plus de détails."
             )
             publish_sns_notification(sns_topic_arn, error_subject, error_message)

        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Internal Server Error', 'error': str(e)})
        }