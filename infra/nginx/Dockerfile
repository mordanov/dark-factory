FROM nginx:alpine

RUN apk add --no-cache gettext

COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY snippets/ /etc/nginx/snippets/

RUN mkdir -p /var/www/certbot

EXPOSE 80

CMD ["/bin/sh", "-c", "envsubst '${UIM_HOST} ${TM_HOST}' < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
