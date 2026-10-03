sudo docker build . -t tt-lol-draft-sim-server
sudo docker-compose down # stop and remove all containers (the db_data volume is kept), docker compose v2 not working. this should be work around -TODO: update to docker compose v2
sudo docker-compose up -d
