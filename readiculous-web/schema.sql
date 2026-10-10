-- Run once locally (and on EC2 / RDS). The app also auto-creates the tables on startup.
CREATE DATABASE IF NOT EXISTS readiculous CHARACTER SET utf8mb4;
USE readiculous;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','reader') NOT NULL DEFAULT 'reader',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS books (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(200) NOT NULL,
  author VARCHAR(120) NOT NULL,
  genre VARCHAR(60) NOT NULL,
  pages INT NOT NULL DEFAULT 0,
  description TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tbr_items (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  book_id INT NOT NULL,
  status ENUM('to_read','reading','finished') NOT NULL DEFAULT 'to_read',
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME NULL,
  UNIQUE KEY uq_user_book (user_id, book_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reading_goals (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  year INT NOT NULL,
  target_books INT NOT NULL,
  UNIQUE KEY uq_user_year (user_id, year),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
